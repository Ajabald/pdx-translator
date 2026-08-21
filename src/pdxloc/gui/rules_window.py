"""The check settings window (Shift+F6).

Why a window rather than a list of checkboxes in «Preferences». The reason for
tuning is always the same: a check complains about a technique the translator uses
on purpose. To tell whether this is that case you need three things at once — how
many times the rule fires on this project, what it says about one particular pair
of rows, and which examples it considers errors itself. A checkbox in a settings
dialog answers none of those questions, and the rule gets switched off blind.

The hit counter is computed on a thread of its own with a connection of its own: a
full pass over 136 thousand rows takes seconds, while a parameter is turned with a
slider. Hence the debounce and the cancelling of the previous count.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from pdxloc import __version__, settings
from pdxloc.core import languages, qa_exchange, qa_rules
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.qa_rules import Rule, RuleSet
from pdxloc.gui import rules_state, theme
from pdxloc.gui.rules_ignores_tab import IgnoresTab
from pdxloc.gui.rules_param_editors import ParamEditors

GLOBAL, PROJECT = "global", "project"
SCOPE_LABELS = {
    GLOBAL: QT_TRANSLATE_NOOP("RulesWindow", "all projects"),
    PROJECT: QT_TRANSLATE_NOOP("RulesWindow", "this project"),
}
SEVERITY_LABELS = {
    qa_rules.ERROR: QT_TRANSLATE_NOOP("RulesWindow", "Error"),
    qa_rules.WARNING: QT_TRANSLATE_NOOP("RulesWindow", "Warning"),
    qa_rules.INFO: QT_TRANSLATE_NOOP("RulesWindow", "Signal"),
}

ROLE_RULE_ID = Qt.UserRole


def severity_label(severity: str) -> str:
    return translate("RulesWindow", SEVERITY_LABELS.get(severity, severity))


# --- the background hit counter ---


class _CountWorker(QObject):
    """How many times each rule fires on the project.

    Opens a read-only connection of its own: sqlite must not be shared between
    threads, and there is nothing to write here anyway.
    """

    done = Signal(dict, int)        # {code: count}, plus the total number of rows
    failed = Signal(str)

    def __init__(self, project_path: Path, rules: RuleSet):
        super().__init__()
        self.project_path = project_path
        self.rules = rules

    def run(self) -> None:
        try:
            from pdxloc.project import read_only_connection

            conn = read_only_connection(self.project_path)
            try:
                rows = conn.execute(
                    """SELECT u.en_text, u.ru_text FROM units u
                       JOIN files f ON f.id = u.file_id
                       WHERE f.project_id = 1 AND u.is_deleted = 0
                         AND u.en_text IS NOT NULL AND u.ru_text IS NOT NULL
                         AND u.status NOT IN ('untranslated', 'ignored')"""
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error as e:
            self.failed.emit(str(e))
            return

        counts: dict[str, int] = {}
        for row in rows:
            for code in self.rules.check(row["en_text"], row["ru_text"]):
                counts[code] = counts.get(code, 0) + 1
        self.done.emit(counts, len(rows))


# --- the «Rules» tab ---


class RulesTab(QWidget):
    rulesEdited = Signal()

    def __init__(self, conn: sqlite3.Connection | None,
                 project_path: Path | None, current_pair=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_path = project_path
        # what fills «Check on a pair» from the button; None means no button
        self.current_pair = current_pair
        self.scope = PROJECT if conn is not None else GLOBAL
        self._counts: dict[str, int] = {}
        self._scanned = 0
        self._thread: QThread | None = None
        self._worker: _CountWorker | None = None
        self._pending = False
        self._loading = False

        # the editable rule set and the preset of each layer — edits to one layer must
        # not leak into another when «Scope» is switched
        self._preset = {
            GLOBAL: qa_rules.preset_of(rules_state.global_overlay()),
            PROJECT: rules_state.project_overlay().get("preset") or qa_rules.CUSTOM,
        }
        self._rules = rules_state.ruleset()

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_top())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_tree())
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes((420, 620))
        layout.addWidget(splitter, 1)

        self._debounce = QTimer(self, singleShot=True, interval=400)
        self._debounce.timeout.connect(self._start_count)

        self._fill_tree()
        self._sync_top()
        self._request_count()

    # --- assembly ---

    def _build_top(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(translate("RulesWindow", "Preset:")))
        self.preset_combo = QComboBox()
        # The order and the mark are the same as in the main window menu: the set that
        # suits the project stands first, the rest behind a separator. There are two
        # shop windows and they must not diverge — a person picks a set now here, now
        # there.
        game, locale = rules_state.game(), rules_state.locale()
        best = qa_rules.recommended(game, locale)
        for name in qa_rules.display_order(game, locale):
            label = qa_rules.preset_label(name)
            if name == best:
                label = fill(translate("QaRules", qa_rules.RECOMMENDED_MARK), label)
            self.preset_combo.addItem(label, name)
            if name == best:
                self.preset_combo.insertSeparator(self.preset_combo.count())
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        row.addWidget(self.preset_combo)

        row.addSpacing(16)
        row.addWidget(QLabel(translate("RulesWindow", "Scope:")))
        self.scope_combo = QComboBox()
        for value in (GLOBAL, PROJECT):
            self.scope_combo.addItem(
                translate("RulesWindow", SCOPE_LABELS[value]), value)
        self.scope_combo.setEnabled(self.conn is not None)
        self.scope_combo.setToolTip(
            translate("RulesWindow",
                      "Where to record the setting: into a file next to the "
                      "application or inside this project"))
        self.scope_combo.currentIndexChanged.connect(self._on_scope)
        row.addWidget(self.scope_combo)
        row.addStretch(1)

        self.import_btn = QPushButton(translate("RulesWindow", "Import…"))
        self.import_btn.setToolTip(translate(
            "RulesWindow", "Take the setting from a file — someone else's or "
                           "your own from another machine"))
        self.import_btn.clicked.connect(self._import)
        row.addWidget(self.import_btn)
        self.export_btn = QPushButton(translate("RulesWindow", "Export…"))
        self.export_btn.setToolTip(translate(
            "RulesWindow", "Write the setting to a file to pass it on"))
        self.export_btn.clicked.connect(self._export)
        row.addWidget(self.export_btn)

        # The reset is two separate actions rather than one button. The old «Reset
        # everything» also silently deleted the layer's own rules: the user's work
        # vanished inside an action that promised to «return the values».
        self.reset_btn = QToolButton()
        self.reset_btn.setText(translate("RulesWindow", "Reset…"))
        self.reset_btn.setPopupMode(QToolButton.InstantPopup)
        self.reset_menu = QMenu(self.reset_btn)
        self.reset_base_action = QAction(
            translate("RulesWindow", "Return built-in rules to the preset"),
            self.reset_menu)
        self.reset_base_action.triggered.connect(self._reset_base)
        self.reset_menu.addAction(self.reset_base_action)
        self.delete_own_action = QAction(
            translate("RulesWindow", "Delete all own rules"), self.reset_menu)
        self.delete_own_action.triggered.connect(self._delete_all_own)
        self.reset_menu.addAction(self.delete_own_action)
        self.reset_btn.setMenu(self.reset_menu)
        row.addWidget(self.reset_btn)
        return row

    def _build_tree(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self._build_tree_widget(), 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton(translate("RulesWindow", "Own rule…"))
        self.add_btn.setToolTip(translate(
            "RulesWindow", "A rule of your own: an expression instead of a "
                           "built-in check"))
        self.add_btn.clicked.connect(self._add_user_rule)
        row.addWidget(self.add_btn)
        self.duplicate_btn = QPushButton(translate("RulesWindow", "Duplicate"))
        self.duplicate_btn.setToolTip(translate(
            "RulesWindow", "A copy of your own rule to edit without losing the "
                           "original. A built-in rule cannot be copied — its "
                           "check is code, not an expression"))
        self.duplicate_btn.clicked.connect(self._duplicate_user_rule)
        row.addWidget(self.duplicate_btn)
        self.delete_btn = QPushButton(translate("RulesWindow", "Delete"))
        self.delete_btn.clicked.connect(self._delete_user_rule)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        box.addLayout(row)
        return page

    def _build_tree_widget(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels((translate("RulesWindow", "Rule"),
                                   translate("RulesWindow", "Hits"),
                                   translate("RulesWindow", "Severity")))
        self.tree.headerItem().setToolTip(
            1, translate("RulesWindow",
                         "How many times the rule fires on this project"))
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        # the counter and the severity fit their content: otherwise the rule name eats
        # the whole width and the numbers the window is opened for slide off the edge
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(lambda *_: self._show_current())
        self.tree.itemChanged.connect(self._on_item_changed)
        return self.tree

    def _build_details(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)

        self.title_label = QLabel()
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        box.addWidget(self.title_label)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        box.addWidget(self.note_label)

        # Two blocks, because these are two different things and the window used not to
        # tell them apart: the **check** is written by the author — on a built-in rule
        # it cannot be touched — while the **settings**, on/off, severity, leniencies,
        # are turned by the translator on any rule. Hence the question «what am I
        # allowed to touch here»: the fields all looked equally editable.
        self.check_box = QGroupBox(translate("RulesWindow", "Check"))
        check_layout = QVBoxLayout(self.check_box)
        self.kind_label = QLabel()
        self.kind_label.setWordWrap(True)
        check_layout.addWidget(self.kind_label)

        self.user_fields = QWidget()
        user_form = QFormLayout(self.user_fields)
        user_form.setContentsMargins(0, 0, 0, 0)
        self.title_edit = QLineEdit()
        self.title_edit.editingFinished.connect(self._on_edited)
        user_form.addRow(translate("RulesWindow", "Name:"), self.title_edit)
        self.message_edit = QLineEdit()
        self.message_edit.setPlaceholderText(
            translate("RulesWindow", "same as the name"))
        self.message_edit.setToolTip(translate(
            "RulesWindow", "What the check will say about the row"))
        self.message_edit.editingFinished.connect(self._on_edited)
        user_form.addRow(translate("RulesWindow", "Message:"), self.message_edit)
        check_layout.addWidget(self.user_fields)
        box.addWidget(self.check_box)

        self.setup_box = QGroupBox(translate("RulesWindow", "Setting"))
        setup_layout = QVBoxLayout(self.setup_box)
        head = QHBoxLayout()
        head.addWidget(QLabel(translate("RulesWindow", "Severity:")))
        self.severity_combo = QComboBox()
        for value in qa_rules.SEVERITIES:
            self.severity_combo.addItem(SEVERITY_LABELS[value], value)
        self.severity_combo.currentIndexChanged.connect(self._on_edited)
        head.addWidget(self.severity_combo)
        head.addStretch(1)
        self.reset_rule_btn = QPushButton(
            translate("RulesWindow", "Return the rule to the preset"))
        self.reset_rule_btn.clicked.connect(self._reset_rule)
        head.addWidget(self.reset_rule_btn)
        setup_layout.addLayout(head)

        params_box = QGroupBox(translate("RulesWindow", "Leniency"))
        params_layout = QVBoxLayout(params_box)
        self.params = ParamEditors()
        self.params.changed.connect(self._on_edited)
        params_layout.addWidget(self.params)
        self.no_params_label = QLabel(translate("RulesWindow", "This rule has no settings."))
        params_layout.addWidget(self.no_params_label)
        # A broken expression silences its own rule quietly — otherwise the check would
        # fall over halfway through a hundred thousand rows — so it is the window's job
        # to say so.
        self.problem_label = QLabel()
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet(f"color: {theme.color('issue.error')}")
        params_layout.addWidget(self.problem_label)
        setup_layout.addWidget(params_box)
        box.addWidget(self.setup_box)

        self.probe_box = self._build_probe()
        box.addWidget(self.probe_box)
        self.examples_label = QLabel(translate(
            "RulesWindow", "Examples — the rule checks itself with them:"))
        self.examples_label.setWordWrap(True)
        box.addWidget(self.examples_label)
        self.examples = QTableWidget(0, 4)
        self.examples.setHorizontalHeaderLabels(
            (translate("RulesWindow", "Original"),
             translate("RulesWindow", "Translation"),
             translate("RulesWindow", "Expected"),
             translate("RulesWindow", "Now")))
        self.examples.verticalHeader().setVisible(False)
        self.examples.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.examples.horizontalHeader().setStretchLastSection(True)
        # the spare height goes to the examples table rather than to the probe field:
        # the field holds two lines of text and there is no point stretching it
        box.addWidget(self.examples, 1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(page)
        return area

    def _build_probe(self) -> QWidget:
        group = QGroupBox(translate("RulesWindow", "Check on a pair"))
        outer = QVBoxLayout(group)
        fields = QHBoxLayout()
        self.probe_en = QPlainTextEdit()
        self.probe_en.setPlaceholderText(translate("RulesWindow", "original"))
        self.probe_ru = QPlainTextEdit()
        self.probe_ru.setPlaceholderText(translate("RulesWindow", "translation"))
        for field in (self.probe_en, self.probe_ru):
            field.setMaximumHeight(60)
            field.textChanged.connect(self._run_probe)
            fields.addWidget(field)
        outer.addLayout(fields)

        row = QHBoxLayout()
        self.take_row_btn = QPushButton(translate("RulesWindow", "Take the current row"))
        self.take_row_btn.setToolTip(
            translate("RulesWindow",
                      "Insert the pair from the row selected in the project table"))
        self.take_row_btn.clicked.connect(self._take_current_row)
        self.take_row_btn.setEnabled(self.current_pair is not None)
        row.addWidget(self.take_row_btn)
        self.probe_label = QLabel()
        self.probe_label.setWordWrap(True)
        row.addWidget(self.probe_label, 1)
        outer.addLayout(row)
        return group

    # --- the tree ---

    def _fill_tree(self) -> None:
        """The tree has two roots: the built-in rules and the user's own.

        There were no roots at all before — the categories went as a flat list,
        and «Own rules» looked like just another category next to «Markup». The
        main thing was invisible: a built-in rule's check cannot be rewritten and
        the rule cannot be deleted, while an own rule belongs to the user
        entirely.
        """
        self._loading = True
        self.tree.clear()

        base_root = self._group(self.tree, translate("RulesWindow", "Built-in rules"))
        base_root.setToolTip(0, translate(
            "RulesWindow", "The check is written in the application: it can be "
                           "switched on and off and made more lenient, but not "
                           "rewritten or deleted"))
        for key, _label in qa_rules.CATEGORIES.items():
            if key == "custom":
                continue        # own rules get a root of their own
            rules = [r for r in self._rules
                     if r.origin != qa_rules.USER and r.category == key
                     and self._for_this_project(r)]
            if rules:
                self._fill_group(self._group(base_root, self._category_title(key)),
                                 rules)

        foreign = [r for r in self._rules
                   if r.origin != qa_rules.USER and not self._for_this_project(r)]
        if foreign:
            # Not hidden: a rule of another language stays silent, and without an
            # explanation that looks like breakage. It can still be switched on by hand.
            group = self._group(base_root,
                                translate("RulesWindow", "Other languages"),
                                expanded=False)
            group.setToolTip(0, translate(
                "RulesWindow", "Rules of a language other than this project's: "
                               "they stay silent, but can be switched on by hand"))
            self._fill_group(group, foreign)

        own_root = self._group(
            self.tree, translate("QaRules", qa_rules.CATEGORIES["custom"]))
        own_root.setToolTip(0, translate(
            "RulesWindow", "Rules of your own: they can be added, edited, "
                           "duplicated and deleted"))
        self._fill_group(own_root, [r for r in self._rules
                                    if r.origin == qa_rules.USER])

        self._loading = False
        self._select_first()
        self._paint_counts()

    def _category_title(self, key: str) -> str:
        """A group label. The language group carries the project language rather
        than the words «Target language».

        A rule stays silent precisely because it is about another language, and the
        group has to name it: «Target language» tells nothing to somebody who is
        translating anyway.
        """
        label = translate("QaRules", qa_rules.CATEGORIES[key])
        locale = rules_state.locale()
        if key == "russian" and locale:
            return f"{label} · {languages.locale_name(locale)}"
        return label

    def _for_this_project(self, rule: Rule) -> bool:
        locale = rules_state.locale()
        return not rule.locale or not locale or rule.locale == locale

    @staticmethod
    def _group(parent, title: str, *, expanded: bool = True) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, (title, "", ""))
        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        item.setExpanded(expanded)
        return item

    def _fill_group(self, parent: QTreeWidgetItem, rules) -> None:
        for rule in rules:
            item = QTreeWidgetItem(parent, (rule.title_text(), "", ""))
            item.setData(0, ROLE_RULE_ID, rule.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if rule.enabled else Qt.Unchecked)
            item.setText(2, severity_label(rule.severity))
            self._mark_modified(item, rule)

    def _select_first(self) -> None:
        for item in self._items():
            self.tree.setCurrentItem(item)
            return

    def _items(self, parent: QTreeWidgetItem | None = None):
        """Every rule in the tree. The walk is recursive: groups gained groups.

        While there were exactly two levels the walk treated the root's children
        as rules. With subgroups such a walk would stop finding rules — silently,
        because the hit counter and the edits both go through it.
        """
        if parent is None:
            for i in range(self.tree.topLevelItemCount()):
                yield from self._items(self.tree.topLevelItem(i))
            return
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, ROLE_RULE_ID):
                yield child
            else:
                yield from self._items(child)

    def _item_of(self, rule_id: str) -> QTreeWidgetItem | None:
        for item in self._items():
            if item.data(0, ROLE_RULE_ID) == rule_id:
                return item
        return None

    def _is_modified(self, rule: Rule) -> bool:
        """The rule differs from what the set makes of it."""
        base = self._base_ruleset().get(rule.id)
        return base is not None and bool(qa_rules.rule_delta(base, rule))

    def _mark_modified(self, item: QTreeWidgetItem, rule: Rule) -> None:
        """A hand-tuned rule is visible in the tree.

        Without the mark, «return to the set» strikes blind: neither what differs
        nor that anything differs at all can be seen.
        """
        modified = self._is_modified(rule)
        font = item.font(0)
        font.setBold(modified)
        item.setFont(0, font)
        item.setToolTip(0, translate(
            "RulesWindow", "Set by hand — differs from the preset") if modified else "")

    def current_rule(self) -> Rule | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return self._rules.get(item.data(0, ROLE_RULE_ID) or "")

    # --- edits ---

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading or column != 0:
            return
        rule = self._rules.get(item.data(0, ROLE_RULE_ID) or "")
        if rule is None:
            return
        self._replace(qa_rules.replace(
            rule, enabled=item.checkState(0) == Qt.Checked))

    def _on_edited(self) -> None:
        if self._loading:
            return
        rule = self.current_rule()
        if rule is None:
            return
        changes = {"severity": self.severity_combo.currentData(),
                   "params": self.params.values(rule)}
        if rule.origin == qa_rules.USER:
            title = self.title_edit.text().strip() or rule.title
            changes["title"] = title
            changes["message"] = self.message_edit.text().strip() or title
        self._replace(qa_rules.replace(rule, **changes))

    def _replace(self, rule: Rule) -> None:
        self._rules = self._rules.with_rule(rule)
        item = self._item_of(rule.id)
        if item is not None:
            self._loading = True
            item.setText(0, rule.title_text())
            item.setCheckState(0, Qt.Checked if rule.enabled else Qt.Unchecked)
            item.setText(2, severity_label(rule.severity))
            self._mark_modified(item, rule)
            self._loading = False
        self.reset_rule_btn.setEnabled(self._is_modified(rule))
        self._show_examples(rule)
        self._show_problems(rule)
        self._run_probe()
        self._request_count()
        self.rulesEdited.emit()

    def _reset_rule(self) -> None:
        rule = self.current_rule()
        if rule is None:
            return
        base = self._base_ruleset().get(rule.id)
        if base is not None:
            self._replace(base)
            self._show_current()

    def _reset_base(self) -> None:
        """Built-in rules go back to the set's values. Own rules are untouched.

        The old «Reset everything» did both at once: rules created by hand vanished
        inside an action that promised to «return the values». Returning to a
        default and deleting somebody's work are different intentions, and they
        must not be confused in one button.
        """
        base = self._base_ruleset()
        changed = [r for r in self._rules
                   if r.origin != qa_rules.USER and self._is_modified(r)]
        if not changed:
            QMessageBox.information(
                self, translate("RulesWindow", "Return built-in rules to the preset"),
                translate("RulesWindow",
                          "The built-in rules already match the preset."))
            return
        if QMessageBox.question(
                self, translate("RulesWindow", "Return built-in rules to the preset"),
                fill(translate("RulesWindow",
                               "Return %1 rules to the preset values? Own rules "
                               "stay as they are."), len(changed))) != QMessageBox.Yes:
            return
        self._rules = RuleSet(
            r if r.origin == qa_rules.USER else (base.get(r.id) or r)
            for r in self._rules)
        self._after_bulk_change()

    def _delete_all_own(self) -> None:
        own = [r for r in self._rules
               if r.origin == qa_rules.USER and not self._base_has(r.id)]
        if not own:
            QMessageBox.information(
                self, translate("RulesWindow", "Delete all own rules"),
                translate("RulesWindow", "There are no own rules in this layer."))
            return
        if QMessageBox.question(
                self, translate("RulesWindow", "Delete all own rules"),
                fill(translate("RulesWindow", "Delete %1 own rules? "
                                              "This cannot be undone."),
                     len(own))) != QMessageBox.Yes:
            return
        doomed = {r.id for r in own}
        self._rules = RuleSet(r for r in self._rules if r.id not in doomed)
        self._after_bulk_change()

    def _after_bulk_change(self) -> None:
        self._fill_tree()
        self._show_current()
        self._request_count()
        self.rulesEdited.emit()

    def _base_ruleset(self) -> RuleSet:
        """The set without this layer's hand edits; the delta is measured from it.

        The translation language passed is the one `rules_state` uses: otherwise
        the delta would be measured against a different base, and «switch the
        Russian rule on» would land in the overlay simply because it counted as
        on here.
        """
        locale = rules_state.locale()
        if self.scope == PROJECT:
            return qa_rules.resolve(rules_state.global_overlay(),
                                    {"preset": self._preset[PROJECT]},
                                    locale=locale)
        return qa_rules.resolve({"preset": self._preset[GLOBAL]}, locale=locale)

    # --- own rules ---

    def _add_user_rule(self) -> None:
        dialog = NewRuleDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        title, kind = dialog.values()
        self._append_user_rule(qa_rules.make_user_rule(
            self._free_id(title), kind, title=title))

    def _duplicate_user_rule(self) -> None:
        """A copy of an own rule. A built-in one cannot be copied: it is code.

        It exists for the same reason as «return to the set» on a built-in rule:
        so an edit can be tried without fear of losing a working rule.
        """
        rule = self.current_rule()
        if rule is None or rule.origin != qa_rules.USER:
            return
        title = fill(translate("RulesWindow", "%1 (copy)"), rule.title)
        self._append_user_rule(qa_rules.replace(
            rule, id=self._free_id(title), title=title,
            message=rule.message if rule.message != rule.title else title))

    def _append_user_rule(self, rule: Rule) -> None:
        self._rules = qa_rules.with_user_rules(self._rules, [rule])
        self._fill_tree()
        item = self._item_of(rule.id)
        if item is not None:
            self.tree.setCurrentItem(item)
        self._show_current()
        self._request_count()
        self.rulesEdited.emit()

    def _free_id(self, title: str) -> str:
        """The rule's name in the files: Latin letters from the title, else a number.

        It reaches more than the overlay: a «not an error» mark stores the rule's
        id next to the row (`qa_ignores`), and the name has no right to change over
        time — renaming a rule in the window does not touch it.
        """
        stem = "".join(c if c.isalnum() and c.isascii() else "_"
                       for c in title.lower()).strip("_")
        stem = "_".join(p for p in stem.split("_") if p)[:40] or "rule"
        taken = {r.id for r in self._rules}
        if stem not in taken and stem not in qa_rules.BY_ID:
            return stem
        n = 2
        while f"{stem}_{n}" in taken or f"{stem}_{n}" in qa_rules.BY_ID:
            n += 1
        return f"{stem}_{n}"

    def _delete_user_rule(self) -> None:
        rule = self.current_rule()
        if rule is None or rule.origin != qa_rules.USER or self._base_has(rule.id):
            return
        if QMessageBox.question(
                self, translate("RulesWindow", "Delete the rule"),
                fill(translate("RulesWindow", "Delete the rule «%1»?"),
                     rule.title_text())) != QMessageBox.Yes:
            return
        self._rules = RuleSet(r for r in self._rules if r.id != rule.id)
        self._after_bulk_change()

    # --- sharing ---

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, translate("RulesWindow", "Export check settings"),
            str(settings.app_root() / f"rules{qa_exchange.SUFFIX}"),
            fill(translate("RulesWindow", "Check settings (*%1)"),
                 qa_exchange.SUFFIX))
        if not path:
            return
        try:
            written = qa_exchange.write(
                Path(path), self._preset[self.scope], self._rules,
                app_version=__version__, locale=rules_state.locale())
        except OSError as e:
            QMessageBox.critical(
                self, translate("RulesWindow", "Export check settings"), str(e))
            return
        QMessageBox.information(
            self, translate("RulesWindow", "Export check settings"),
            fill(translate("RulesWindow", "Written: %1"), str(written)))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, translate("RulesWindow", "Import check settings"),
            str(settings.app_root()),
            fill(translate("RulesWindow", "Check settings (*%1);;All files (*)"),
                 qa_exchange.SUFFIX))
        if not path:
            return
        try:
            bundle = qa_exchange.read(Path(path))
        except qa_exchange.ExchangeError as e:
            QMessageBox.critical(
                self, translate("RulesWindow", "Import check settings"),
                fill(translate("RulesWindow", "The file cannot be read: %1"),
                     str(e)))
            return

        lines = [fill(translate("RulesWindow", "Preset: %1"),
                      qa_rules.preset_label(bundle.preset)),
                 fill(translate("RulesWindow", "Rules edited: %1"),
                      len(bundle.changed)),
                 fill(translate("RulesWindow", "Own rules: %1"), len(bundle.added))]
        if bundle.skipped:
            lines.append(fill(
                translate("RulesWindow",
                          "Not understood and skipped: %1 (%2)"),
                len(bundle.skipped), ", ".join(bundle.skipped[:5])))
        lines.append("")
        lines.append(fill(
            translate("RulesWindow", "Replace the setting for «%1»?"),
            translate("RulesWindow", SCOPE_LABELS[self.scope])))
        if QMessageBox.question(
                self, translate("RulesWindow", "Import check settings"),
                "\n".join(lines)) != QMessageBox.Yes:
            return

        self._preset[self.scope] = bundle.preset
        self._rules = bundle.ruleset(rules_state.locale())
        self._fill_tree()
        self._sync_top()
        self._show_current()
        self._request_count()
        self.rulesEdited.emit()

    # --- the preset and the scope ---

    def _on_preset(self) -> None:
        if self._loading:
            return
        chosen = self.preset_combo.currentData()
        if chosen == self._preset[self.scope]:
            return
        self._preset[self.scope] = chosen
        # A preset changes the base, so the layer's hand edits are cleared: keeping them
        # would show a set the user never assembled by a single deliberate action. Own
        # rules stay, though: a preset is about the strictness of the built-in checks and
        # says nothing about rules created by hand.
        base = self._base_ruleset()
        own = [r for r in self._rules
               if r.origin == qa_rules.USER and base.get(r.id) is None]
        self._rules = qa_rules.with_user_rules(base, own)
        self._after_bulk_change()

    def _on_scope(self) -> None:
        if self._loading:
            return
        self.scope = self.scope_combo.currentData()
        self._sync_top()
        # «Delete» and «Reset rule» answer for the layer: a rule that arrived from below
        # can only be switched off here, and the buttons have to show that
        self._show_current()

    def _sync_top(self) -> None:
        self._loading = True
        self.scope_combo.setCurrentIndex(
            self.scope_combo.findData(self.scope))
        self.preset_combo.setCurrentIndex(
            self.preset_combo.findData(self._preset[self.scope]))
        note = translate(
            "QaRules", qa_rules.PRESET_NOTES.get(self._preset[self.scope], ""))
        # The language layer arrives with the project. Without a project there is none,
        # and the issue counts here honestly differ from the ones a person sees at work
        # — staying silent would let that difference be read as a loss.
        if not rules_state.locale():
            note += "\n\n" + translate(
                "RulesWindow",
                "The inflection helpers of the target language are added when a "
                "project is open — they come with its translation language.")
        self.preset_combo.setToolTip(note)
        self._loading = False

    # --- the panel on the right ---

    def _show_current(self) -> None:
        rule = self.current_rule()
        if rule is None:
            # a group is selected rather than a rule: the rule buttons have nothing to act
            # on
            for button in (self.delete_btn, self.duplicate_btn, self.reset_rule_btn):
                button.setEnabled(False)
            return
        own = rule.origin == qa_rules.USER
        self._loading = True
        self.title_label.setText(rule.title_text())
        self.note_label.setText(rule.note_text() or rule.message_text())
        self.severity_combo.setCurrentIndex(
            self.severity_combo.findData(rule.severity))

        self.user_fields.setVisible(own)
        if own:
            kind = qa_rules.KINDS.get(rule.kind)
            self.check_box.setTitle(fill(
                translate("RulesWindow", "Check · %1"),
                translate("QaRules", kind.title) if kind else rule.kind))
            self.kind_label.setText(
                translate("QaRules", kind.hint) if kind else "")
            self.title_edit.setText(rule.title)
            self.message_edit.setText(
                "" if rule.message == rule.title else rule.message)
        else:
            self.check_box.setTitle(translate("RulesWindow", "Check"))
            # The lock is words rather than an icon: an icon would have to be explained
            self.kind_label.setText(translate(
                "RulesWindow",
                "🔒 Built-in rule: the check and its wording live in the "
                "application. It can be switched off and made more lenient, "
                "but not rewritten or deleted."))

        self.params.set_rule(rule)
        self.params.setVisible(bool(rule.params))
        self.no_params_label.setVisible(not rule.params)
        self.reset_rule_btn.setEnabled(self._is_modified(rule))
        # Delete and duplicate apply only to what was created in this layer: a rule from
        # the layer below is a stranger here and can only be switched off
        deletable = own and not self._base_has(rule.id)
        self.delete_btn.setEnabled(deletable)
        self.duplicate_btn.setEnabled(own)
        self.delete_btn.setToolTip(
            translate("RulesWindow",
                      "The rule is set for all projects — here it can only be "
                      "switched off")
            if own and not deletable else "")
        self._loading = False
        self._show_examples(rule)
        self._show_problems(rule)
        self._run_probe()

    def _base_has(self, rule_id: str) -> bool:
        """The rule arrived from below: from the built-in set or a neighbouring layer."""
        return self._base_ruleset().get(rule_id) is not None

    def _show_problems(self, rule: Rule) -> None:
        names = [n for n in ("pattern", "source") if n in rule.params]
        if rule.params.get("target_as_regex"):
            names.append("target")
        problems = []
        for name in names:
            value = str(rule.params.get(name, ""))
            error = qa_rules.regex_error(value) or qa_rules.regex_warning(value)
            if error:
                problems.append(f"{name}: {error}")
        self.problem_label.setText("\n".join(problems))
        self.problem_label.setVisible(bool(problems))

    def _show_examples(self, rule: Rule) -> None:
        """The examples are checked with the rule forced on.

        Otherwise a disabled rule would show «silent» on its own example of an
        error, and the column would stop answering the question «are the
        parameters set right?» — the one it exists for.
        """
        pairs = [(en, ru, True) for en, ru in rule.example_bad]
        pairs += [(en, ru, False) for en, ru in rule.example_ok]
        # An empty table under the heading «the rule checks itself with these» promises
        # what is not there: an own rule has no examples at all — the probe stands in
        # for them.
        self.examples.setVisible(bool(pairs))
        self.examples_label.setText(translate(
            "RulesWindow", "Examples — the rule checks itself with them:")
            if pairs else translate(
            "RulesWindow", "This rule has no self-check examples — try it on a "
                           "pair above."))
        self.examples.setRowCount(len(pairs))
        single = self._rules.restricted_to({rule.id})
        for row, (en, ru, should_fire) in enumerate(pairs):
            fires = bool(single.check(en, ru))
            fires_word = translate("RulesWindow", "fires")
            silent_word = translate("RulesWindow", "silent")
            cells = (en, ru,
                     fires_word if should_fire else silent_word,
                     fires_word if fires else silent_word)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 3 and fires != should_fire:
                    item.setForeground(theme.qcolor("issue.error"))
                self.examples.setItem(row, col, item)
        self.examples.resizeColumnsToContents()

    def _run_probe(self) -> None:
        en = self.probe_en.toPlainText()
        ru = self.probe_ru.toPlainText()
        if not en and not ru:
            self.probe_label.setText("")
            return
        codes = self._rules.check(en, ru)
        if not codes:
            self.probe_label.setText(translate("RulesWindow", "No issues."))
            return
        self.probe_label.setText("; ".join(self._rules.message(c) for c in codes))

    def set_probe(self, en: str, ru: str) -> None:
        self.probe_en.setPlainText(en)
        self.probe_ru.setPlainText(ru)

    def _take_current_row(self) -> None:
        pair = self.current_pair() if self.current_pair else None
        if pair:
            self.set_probe(pair[0] or "", pair[1] or "")

    # --- the hit counter ---

    def _request_count(self) -> None:
        if self.project_path is None:
            return
        self._debounce.start()

    def _start_count(self) -> None:
        if self.project_path is None:
            return
        if self._thread is not None:
            self._pending = True       # a count is already running: repeat after it
            return
        self._thread = QThread(self)
        self._worker = _CountWorker(self.project_path, self._rules)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_counts)
        self._worker.failed.connect(self._on_count_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_thread_finished(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        if self._pending:
            self._pending = False
            self._start_count()

    def _on_counts(self, counts: dict, scanned: int) -> None:
        self._counts = counts
        self._scanned = scanned
        self._paint_counts()

    def _on_count_failed(self, message: str) -> None:
        """The count failed: the column empties and the rule settings are unharmed."""
        self._counts = {}
        self._scanned = 0
        self._paint_counts()

    def _paint_counts(self) -> None:
        for item in self._items():
            rule_id = item.data(0, ROLE_RULE_ID)
            rule = self._rules.get(rule_id or "")
            if rule is None:
                continue
            if rule_id in qa_rules.PROJECT_WIDE:
                item.setText(1, translate("RulesWindow", "project-wide"))
            elif not rule.enabled:
                item.setText(1, "—")
            elif not self._counts and not self._scanned:
                item.setText(1, "")
            else:
                item.setText(1, str(self._counts.get(rule_id, 0)))

    def status_text(self) -> str:
        if self.project_path is None:
            return translate("RulesWindow",
                             "The hit counter needs an open project.")
        if not self._scanned:
            return translate("RulesWindow", "Counting the hits…")
        return fill(translate(
            "RulesWindow", "Hits counted on %1 translated rows of the project."),
            self._scanned)

    # --- saving ---

    def overlays(self) -> tuple[dict, dict]:
        """What to write into the global layer and into the project layer.

        The translation language passed here is the same as in `_base_ruleset`:
        it is part of the base, and without it the delta would pick up «switch off
        the rule of another language» — an edit the user never made.
        """
        locale = rules_state.locale()
        if self.scope == PROJECT:
            project = qa_rules.make_overlay(
                self._preset[PROJECT], self._rules,
                under=rules_state.global_overlay(), locale=locale)
            return rules_state.global_overlay(), project
        glob = qa_rules.make_overlay(self._preset[GLOBAL], self._rules,
                                     locale=locale)
        return glob, rules_state.project_overlay()

    def shutdown(self) -> None:
        """A pending count must not outlive the window: the database is sometimes
        already closed."""
        self._debounce.stop()
        self._pending = False
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)


# --- creating an own rule ---


class NewRuleDialog(QDialog):
    """Two fields: what to call it and of what kind.

    There is nothing else to ask here: the severity, the message text and the
    parameters are edited in the same place as for the built-in rules, in the
    window's panel. A dialog that asks for everything at once forces you to choose
    an expression blind, seeing neither the hit counter nor a probe on a pair of
    rows.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("RulesWindow", "Own rule"))
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(
            translate("RulesWindow", "for example: No ellipsis as one character"))
        form.addRow(translate("RulesWindow", "Name:"), self.title_edit)
        self.kind_combo = QComboBox()
        for kind_id in qa_rules.KIND_ORDER:
            kind = qa_rules.KINDS[kind_id]
            self.kind_combo.addItem(translate("QaRules", kind.title), kind_id)
        self.kind_combo.currentIndexChanged.connect(self._show_hint)
        form.addRow(translate("RulesWindow", "Kind:"), self.kind_combo)
        layout.addLayout(form)

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self._ok = box.button(QDialogButtonBox.Ok)
        self.title_edit.textChanged.connect(
            lambda text: self._ok.setEnabled(bool(text.strip())))
        self._ok.setEnabled(False)
        self._show_hint()

    def _show_hint(self) -> None:
        kind = qa_rules.KINDS[self.kind_combo.currentData()]
        self.hint_label.setText(translate("QaRules", kind.hint))

    def _accept(self) -> None:
        if self.title_edit.text().strip():
            self.accept()

    def values(self) -> tuple[str, str]:
        return self.title_edit.text().strip(), self.kind_combo.currentData()




# --- the window ---


class RulesWindow(QDialog):
    """The check settings: the rules and the silenced issues."""

    rulesChanged = Signal()

    def __init__(self, conn: sqlite3.Connection | None = None,
                 project_path: Path | None = None, parent=None,
                 initial_tab: int = 0, current_pair=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("RulesWindow", "Check settings"))
        self.setMinimumSize(1000, 640)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.rules_tab = RulesTab(conn, project_path, current_pair)
        self.ignores_tab = IgnoresTab(conn)
        self.tabs.addTab(self.rules_tab, translate("RulesWindow", "Rules"))
        self.tabs.addTab(self.ignores_tab,
                         translate("RulesWindow", "Marked «not an error»"))
        self.tabs.setCurrentIndex(initial_tab)
        layout.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Save).setText(
            translate("RulesWindow", "Apply and close"))
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        bottom.addWidget(box)
        layout.addLayout(bottom)

        self.rules_tab.rulesEdited.connect(self._show_status)
        self.ignores_tab.changed.connect(self.rulesChanged)
        self.tabs.currentChanged.connect(lambda _: self._show_status())
        self._show_status()

    def select_rule(self, rule_id: str) -> None:
        """Open the window straight on a rule, from the button in the F6 report."""
        item = self.rules_tab._item_of(rule_id)
        if item is not None:
            self.tabs.setCurrentIndex(0)
            self.rules_tab.tree.setCurrentItem(item)

    def _show_status(self) -> None:
        widget = self.tabs.currentWidget()
        self.status_label.setText(widget.status_text())

    def _save(self) -> None:
        glob, project = self.rules_tab.overlays()
        rules_state.save_global(glob)
        if self.conn is not None:
            rules_state.save_project(self.conn, project)
        self.rulesChanged.emit()
        self.accept()

    def _stop(self) -> None:
        self.rules_tab.shutdown()
        self.ignores_tab.shutdown()

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._stop()
        super().done(result)

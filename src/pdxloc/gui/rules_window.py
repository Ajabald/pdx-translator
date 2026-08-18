"""Окно настройки проверок (Shift+F6).

Зачем окно, а не список галок в «Параметрах». Повод к настройке всегда один и
тот же: проверка ругается на приём, которым переводчик пользуется намеренно.
Чтобы понять, тот ли это случай, нужно видеть три вещи разом — сколько раз
правило срабатывает на этом проекте, что оно скажет на конкретной паре строк и
какие примеры оно само считает ошибкой. Галка в диалоге настроек не отвечает ни
на один из вопросов, и правило выключают вслепую.

Счётчик срабатываний считается в отдельном потоке со своим соединением: полный
проход по 136 тысячам строк занимает секунды, а параметр крутят ползунком.
Отсюда дебаунс и отмена предыдущего замера.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from pdxloc import __version__, settings
from pdxloc.core import languages, qa, qa_exchange, qa_rules
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.qa_rules import Rule, RuleSet
from pdxloc.gui import rules_state, theme

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


# --- фоновый счётчик срабатываний ----------------------------------------


class _CountWorker(QObject):
    """Сколько раз каждое правило срабатывает на проекте.

    Открывает своё соединение на чтение: делить sqlite между потоками нельзя,
    а писать сюда нечего.
    """

    done = Signal(dict, int)        # {код: сколько}, всего строк
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


# --- редакторы параметров ------------------------------------------------


class _ParamEditors(QWidget):
    """Поля параметров правила, собранные по типу значения.

    Тип берём у значения по умолчанию: список строк — поле через запятую,
    целое — счётчик, `bool` — галка, строка из фиксированного набора —
    выпадающий список. Отдельной схемы типов нет намеренно: она разошлась бы
    с самими параметрами при первой же правке `qa_rules.py`.
    """

    changed = Signal()

    # параметры, у которых значения — перечисление, а не свободный текст
    CHOICES = {
        "compare": ("multiset", "set", "count"),
        "direction": ("any", "fewer", "more"),
        "mode": ("forbid", "require"),
    }
    HINTS = {
        "ignore_extra_heads": QT_TRANSLATE_NOOP(
            "RulesWindow", "Comma separated: Concept, Select_CString"),
        "allow_extra_tags": QT_TRANSLATE_NOOP(
            "RulesWindow", "Comma separated: #L, #P"),
        "ignore_tags": QT_TRANSLATE_NOOP("RulesWindow", "Comma separated"),
        "ending_wrappers": QT_TRANSLATE_NOOP("RulesWindow", "Comma separated"),
        "ending_suffixes": QT_TRANSLATE_NOOP("RulesWindow", "Comma separated"),
        "verbs": QT_TRANSLATE_NOOP(
            "RulesWindow",
            "Comma separated; fragments of a regular expression are allowed"),
        "compare": QT_TRANSLATE_NOOP(
            "RulesWindow", "multiset — with counts, set — composition only, "
                           "count — the number only"),
        "direction": QT_TRANSLATE_NOOP(
            "RulesWindow", "any — any discrepancy, fewer — lost ones only, "
                           "more — extra ones only"),
        "allow_replacement": QT_TRANSLATE_NOOP(
            "RulesWindow", "The wrapper is not «on top of» but «instead of» the "
                           "reference — 59% of all bracket discrepancies"),
        "compare_with_source": QT_TRANSLATE_NOOP(
            "RulesWindow", "Stay silent if the same space is in the original"),
        "only_if_source_balanced": QT_TRANSLATE_NOOP(
            "RulesWindow", "Stay silent if the original itself is unbalanced"),
        "ignore_if_in_source": QT_TRANSLATE_NOOP(
            "RulesWindow", "Stay silent if the double space is in the original"),
        "ignore_flags": QT_TRANSLATE_NOOP(
            "RulesWindow", "Do not count formatting flags like |E as a discrepancy"),
        "strip_markup_first": QT_TRANSLATE_NOOP(
            "RulesWindow", "Count brackets after stripping the markup"),
        "only_if_all_lost": QT_TRANSLATE_NOOP(
            "RulesWindow", "Complain only when not a single variable is left in "
                           "the translation, and stay silent when the set merely "
                           "differs"),
        # параметры своих правил
        "pattern": QT_TRANSLATE_NOOP(
            "RulesWindow", "A regular expression; a match counts whole, "
                           "brackets inside do not change that"),
        "source": QT_TRANSLATE_NOOP(
            "RulesWindow", "A regular expression over the original"),
        "target": QT_TRANSLATE_NOOP(
            "RulesWindow", "What must be in the translation. Groups of the "
                           "original are substituted as \\1"),
        "target_as_regex": QT_TRANSLATE_NOOP(
            "RulesWindow", "Treat the answer as a regular expression too. Off, "
                           "the answer is searched as plain text — that is why "
                           "$\\1$ works"),
        "mode": QT_TRANSLATE_NOOP(
            "RulesWindow", "forbid — fires when found, require — fires when "
                           "missing"),
        "ignore_case": QT_TRANSLATE_NOOP("RulesWindow", "Ignore the case"),
        "pairs": QT_TRANSLATE_NOOP(
            "RulesWindow", "Comma separated, two characters each: «», ()"),
        "chars": QT_TRANSLATE_NOOP(
            "RulesWindow", "In a row, without separators: …—"),
        "tolerance": QT_TRANSLATE_NOOP(
            "RulesWindow", "How big a difference is still not an issue"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._widgets: dict[str, QWidget] = {}
        self._kinds: dict[str, type] = {}

    def set_rule(self, rule: Rule) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()
        self._kinds.clear()

        for name, value in rule.params.items():
            widget = self._make(name, value)
            if widget is None:
                continue
            hint = self.HINTS.get(name)
            if hint:
                widget.setToolTip(translate("RulesWindow", hint))
            self._widgets[name] = widget
            self._kinds[name] = type(value)
            self._form.addRow(name, widget)

    def _make(self, name: str, value) -> QWidget | None:
        if isinstance(value, bool):
            box = QCheckBox()
            box.setChecked(value)
            box.toggled.connect(lambda _: self.changed.emit())
            return box
        if isinstance(value, int):
            spin = QSpinBox()
            spin.setRange(0, 10_000)
            spin.setValue(value)
            spin.valueChanged.connect(lambda _: self.changed.emit())
            return spin
        if isinstance(value, float):
            edit = QLineEdit(str(value))
            edit.editingFinished.connect(self.changed.emit)
            return edit
        if isinstance(value, (list, tuple)):
            edit = QLineEdit(", ".join(str(v) for v in value))
            edit.editingFinished.connect(self.changed.emit)
            return edit
        if isinstance(value, str):
            choices = self.CHOICES.get(name)
            if choices:
                combo = QComboBox()
                combo.addItems(choices)
                combo.setCurrentText(value)
                combo.currentTextChanged.connect(lambda _: self.changed.emit())
                return combo
            edit = QLineEdit(value)
            edit.editingFinished.connect(self.changed.emit)
            return edit
        return None

    def values(self, rule: Rule) -> dict:
        """Значения полей, приведённые к типу параметра по умолчанию."""
        out: dict = {}
        for name, default in rule.params.items():
            widget = self._widgets.get(name)
            if widget is None:
                out[name] = default
                continue
            out[name] = self._read(widget, default)
        return out

    @staticmethod
    def _read(widget: QWidget, default):
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        text = widget.text().strip()
        if isinstance(default, (list, tuple)):
            return [p.strip() for p in text.split(",") if p.strip()]
        if isinstance(default, float):
            try:
                return float(text.replace(",", "."))
            except ValueError:
                return default
        return text


# --- вкладка «Правила» ---------------------------------------------------


class RulesTab(QWidget):
    rulesEdited = Signal()

    def __init__(self, conn: sqlite3.Connection | None,
                 project_path: Path | None, current_pair=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_path = project_path
        # чем заполнить «Проверить на паре» по кнопке; None — кнопки нет
        self.current_pair = current_pair
        self.scope = PROJECT if conn is not None else GLOBAL
        self._counts: dict[str, int] = {}
        self._scanned = 0
        self._thread: QThread | None = None
        self._worker: _CountWorker | None = None
        self._pending = False
        self._loading = False

        # редактируемый набор и пресет каждого слоя — правки одного слоя не
        # должны утекать в другой при переключении «Область»
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

    # --- сборка ---

    def _build_top(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(translate("RulesWindow", "Preset:")))
        self.preset_combo = QComboBox()
        for name in qa_rules.PRESET_ORDER:
            self.preset_combo.addItem(
                translate("QaRules", qa_rules.PRESET_LABELS[name]), name)
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

        # Сброс — двумя разными действиями, а не одной кнопкой. Прежняя
        # «Сбросить всё» заодно молча удаляла свои правила слоя: работа
        # пользователя исчезала в действии, обещавшем «вернуть значения».
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
        # счётчик и серьёзность — по содержимому: иначе имя правила съедает
        # всю ширину, а числа, ради которых окно и открывают, уезжают за край
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

        # Два блока, потому что это две разные вещи, и раньше окно их не
        # различало: **проверку** пишет автор — у базового правила её не
        # тронуть, — а **настройку** (вкл/выкл, серьёзность, послабления) крутит
        # переводчик у любого правила. Отсюда и был вопрос «что тут можно
        # трогать»: поля выглядели одинаково доступными.
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
        self.params = _ParamEditors()
        self.params.changed.connect(self._on_edited)
        params_layout.addWidget(self.params)
        self.no_params_label = QLabel(translate("RulesWindow", "This rule has no settings."))
        params_layout.addWidget(self.no_params_label)
        # Битое выражение гасит своё правило молча (иначе проверка падала бы
        # посреди прохода по сотне тысяч строк) — сказать об этом обязано окно.
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
        # свободную высоту отдаём таблице примеров, а не полю пробы: поле
        # держит две строки текста, и растягивать его не за чем
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

    # --- дерево ---

    def _fill_tree(self) -> None:
        """Дерево двумя корнями: базовые правила и свои.

        Раньше корней не было вовсе — категории шли плоским списком, и «Свои
        правила» выглядели такой же категорией, как «Разметка». Из окна не было
        видно главного: у базового правила проверку не переписать и его не
        удалить, а своё принадлежит целиком пользователю.
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
                continue        # своим правилам отведён свой корень
            rules = [r for r in self._rules
                     if r.origin != qa_rules.USER and r.category == key
                     and self._for_this_project(r)]
            if rules:
                self._fill_group(self._group(base_root, self._category_title(key)),
                                 rules)

        foreign = [r for r in self._rules
                   if r.origin != qa_rules.USER and not self._for_this_project(r)]
        if foreign:
            # Не прячем: правило чужого языка молчит, и без объяснения это
            # выглядит поломкой. Включить его вручную по-прежнему можно.
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
        """Подпись группы. У языковой — с языком проекта, а не «Язык перевода».

        Правило молчит именно потому, что оно про другой язык, и группа обязана
        это назвать: иначе «Язык перевода» ничего не сообщает тому, кто и так
        переводит.
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
        """Все правила дерева. Обход рекурсивный: у групп появились группы.

        Пока уровней было ровно два, обход считал детей корня правилами. С
        подгруппами такой обход перестал бы находить правила — молча, потому
        что и счётчик срабатываний, и правки ходят через него же.
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
        """Правило отличается от того, каким его задаёт набор."""
        base = self._base_ruleset().get(rule.id)
        return base is not None and bool(qa_rules.rule_delta(base, rule))

    def _mark_modified(self, item: QTreeWidgetItem, rule: Rule) -> None:
        """Настроенное вручную правило видно в дереве.

        Без пометки «вернуть к набору» бьёт вслепую: не видно ни того, что
        отличается, ни того, что отличается хоть что-то.
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

    # --- правки ---

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
        """Базовые правила — к значениям набора. Свои не трогаем.

        Прежняя «Сбросить всё» делала и то и другое разом: правила, заведённые
        руками, исчезали в действии, обещавшем «вернуть значения». Возврат к
        умолчанию и удаление чужой работы — разные намерения, и путать их в
        одной кнопке нельзя.
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
        """Набор без ручных правок текущего слоя — от него считается дельта.

        Язык перевода передаётся тот же, что использует `rules_state`: иначе
        дельта посчиталась бы относительно другого основания, и в оверлей
        попало бы «включить русское правило» просто потому, что здесь оно
        считалось включённым.
        """
        locale = rules_state.locale()
        if self.scope == PROJECT:
            return qa_rules.resolve(rules_state.global_overlay(),
                                    {"preset": self._preset[PROJECT]},
                                    locale=locale)
        return qa_rules.resolve({"preset": self._preset[GLOBAL]}, locale=locale)

    # --- свои правила ---

    def _add_user_rule(self) -> None:
        dialog = NewRuleDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        title, kind = dialog.values()
        self._append_user_rule(qa_rules.make_user_rule(
            self._free_id(title), kind, title=title))

    def _duplicate_user_rule(self) -> None:
        """Копия своего правила. Базовое скопировать нечем — это код.

        Нужна затем же, зачем «вернуть к набору» у базового: чтобы правку можно
        было пробовать, не боясь потерять работающее правило.
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
        """Имя правила в файлах. Латиницей из заголовка, иначе по счёту.

        Оно попадает не только в оверлей: пометка «это не ошибка» хранит код
        правила рядом со строкой (`qa_ignores`), и меняться со временем имя не
        имеет права — переименование правила в окне его не трогает.
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

    # --- обмен ---

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
                      translate("QaRules", qa_rules.PRESET_LABELS[bundle.preset])),
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

    # --- пресет и область ---

    def _on_preset(self) -> None:
        if self._loading:
            return
        chosen = self.preset_combo.currentData()
        if chosen == self._preset[self.scope]:
            return
        self._preset[self.scope] = chosen
        # Пресет меняет основание, поэтому ручные правки слоя сбрасываются:
        # оставить их значило бы показать набор, который пользователь не
        # собирал ни одним осознанным действием. Свои правила при этом
        # остаются: пресет — про строгость встроенных проверок и о заведённых
        # руками правилах не говорит ничего.
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
        # «Удалить» и «Сбросить правило» отвечают за слой: правило, приехавшее
        # снизу, здесь можно только выключить — и кнопки обязаны это показать
        self._show_current()

    def _sync_top(self) -> None:
        self._loading = True
        self.scope_combo.setCurrentIndex(
            self.scope_combo.findData(self.scope))
        self.preset_combo.setCurrentIndex(
            self.preset_combo.findData(self._preset[self.scope]))
        self.preset_combo.setToolTip(translate(
            "QaRules", qa_rules.PRESET_NOTES.get(self._preset[self.scope], "")))
        self._loading = False

    # --- панель справа ---

    def _show_current(self) -> None:
        rule = self.current_rule()
        if rule is None:
            # выбрана группа, а не правило: кнопки правила ни к чему не относятся
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
            # Замок словами, а не значком: значок пришлось бы объяснять
            self.kind_label.setText(translate(
                "RulesWindow",
                "🔒 Built-in rule: the check and its wording live in the "
                "application. It can be switched off and made more lenient, "
                "but not rewritten or deleted."))

        self.params.set_rule(rule)
        self.params.setVisible(bool(rule.params))
        self.no_params_label.setVisible(not rule.params)
        self.reset_rule_btn.setEnabled(self._is_modified(rule))
        # Удалить и дублировать можно только то, что заведено в этом слое:
        # правило нижнего слоя здесь чужое, его можно лишь выключить
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
        """Правило приехало снизу — из встроенных или из соседнего слоя."""
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
        """Примеры считаем правилом, принудительно включённым.

        Иначе выключенное правило показывало бы «молчит» на своём же примере
        ошибки, и колонка перестала бы отвечать на вопрос «а параметры-то
        настроены верно?» — ради которого она и заведена.
        """
        pairs = [(en, ru, True) for en, ru in rule.example_bad]
        pairs += [(en, ru, False) for en, ru in rule.example_ok]
        # Пустая таблица под заголовком «правило проверяет себя ими» обещает то,
        # чего нет: у своего правила примеров и не бывает — вместо них проба.
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

    # --- счётчик срабатываний ---

    def _request_count(self) -> None:
        if self.project_path is None:
            return
        self._debounce.start()

    def _start_count(self) -> None:
        if self.project_path is None:
            return
        if self._thread is not None:
            self._pending = True       # замер уже идёт — повторим после него
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
        """Замер не удался — колонка пустеет, настройка правил не страдает."""
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

    # --- сохранение ---

    def overlays(self) -> tuple[dict, dict]:
        """Что записать в глобальный слой и в слой проекта.

        Язык перевода передаётся тот же, что в `_base_ruleset`: он входит в
        основание, и без него в дельту попало бы «выключить правило чужого
        языка» — правка, которой пользователь не делал.
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
        """Отложенный замер не должен пережить окно: база бывает уже закрыта."""
        self._debounce.stop()
        self._pending = False
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)


# --- заведение своего правила --------------------------------------------


class NewRuleDialog(QDialog):
    """Два поля: как назвать и какого вида.

    Больше здесь спрашивать нечего: серьёзность, текст замечания и параметры
    правятся там же, где у встроенных правил, — в панели окна. Диалог, который
    спрашивает всё сразу, заставляет выбирать выражение вслепую, не видя ни
    счётчика срабатываний, ни пробы на паре строк.
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


# --- вкладка «Помеченные „не ошибка“» ------------------------------------


class IgnoresTab(QWidget):
    """Заглушённые замечания и возврат их в проверку.

    `qa.unignore_issue` существовал с самого начала, но из интерфейса не
    вызывался нигде: пометив замечание ложным по ошибке, вернуть его было
    нельзя иначе как правкой базы руками.
    """

    changed = Signal()

    def __init__(self, conn: sqlite3.Connection | None, parent=None):
        super().__init__(parent)
        self.conn = conn
        layout = QVBoxLayout(self)

        # Пустой список ничего не сообщает о том, что это за вкладка и как сюда
        # что-то попадает, — а попадает оно из другого окна, из отчёта F6.
        # Пустое состояние обязано отвечать на вопрос «что это», иначе его
        # задают вслух.
        self.empty_label = QLabel(translate(
            "RulesWindow",
            "Nothing has been silenced yet.\n\n"
            "This is where issues go after the «Not an error» button in the "
            "check report (F6): a silenced issue stops showing up both in the "
            "report and in the «!» column of the table. From here it can be "
            "put back into the check."))
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setEnabled(False)      # приглушённый, это не ошибка
        layout.addWidget(self.empty_label, 1)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.return_btn = QPushButton(translate("RulesWindow", "Return to the check"))
        self.return_btn.clicked.connect(self._return_selected)
        row.addWidget(self.return_btn)
        self.return_all_btn = QPushButton(translate("RulesWindow", "Return all"))
        self.return_all_btn.clicked.connect(self._return_all)
        row.addWidget(self.return_all_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        if self.conn is None:
            return
        try:
            rows = self.conn.execute(
                """SELECT g.unit_id, g.code, u.key, f.rel_path
                   FROM qa_ignores g
                   JOIN units u ON u.id = g.unit_id
                   JOIN files f ON f.id = u.file_id
                   ORDER BY f.rel_path, u.key"""
            ).fetchall()
        except sqlite3.Error:
            rows = []
        rules = rules_state.ruleset()
        for row in rows:
            item = QListWidgetItem(
                f"{row['key']} — {rules.message(row['code'])}  ({row['rel_path']})")
            item.setData(Qt.UserRole, (row["unit_id"], row["code"]))
            self.list.addItem(item)
        self.return_btn.setEnabled(bool(rows))
        self.return_all_btn.setEnabled(bool(rows))
        # Список и объяснение делят одно место: пустой список показывать не за
        # чем, а объяснение при непустом только мешало бы
        self.list.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)

    def status_text(self) -> str:
        n = self.list.count()
        if not n:
            return translate("RulesWindow", "Nothing is marked «not an error».")
        return fill(translate("RulesWindow", "Marked «not an error»: %1."), n)

    def _return(self, pairs) -> None:
        if self.conn is None or not pairs:
            return
        for unit_id, code in pairs:
            qa.unignore_issue(self.conn, unit_id, code)
        self.reload()
        self.changed.emit()

    def _return_selected(self) -> None:
        self._return([i.data(Qt.UserRole) for i in self.list.selectedItems()])

    def _return_all(self) -> None:
        if not self.list.count():
            return
        if QMessageBox.question(
                self, translate("RulesWindow", "Return all"),
                fill(translate("RulesWindow",
                               "Return all %1 issues to the check?"),
                     self.list.count())
        ) != QMessageBox.Yes:
            return
        self._return([self.list.item(i).data(Qt.UserRole)
                      for i in range(self.list.count())])

    def shutdown(self) -> None:
        pass


# --- окно ----------------------------------------------------------------


class RulesWindow(QDialog):
    """Настройка проверок: правила и заглушённые замечания."""

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
        """Открыть окно сразу на нужном правиле — из кнопки в отчёте F6."""
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

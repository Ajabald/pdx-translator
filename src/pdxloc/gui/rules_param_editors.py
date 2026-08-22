"""Fields for rule parameters, built from the type of the value.

Split out of `rules_window.py`: the widget stands alone, knows nothing about the
rules window and made up a sixth of its bulk. The window became readable and the
editors became testable on their own.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLineEdit, QPlainTextEdit, QSpinBox,
    QWidget,
)

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.qa_rules import Rule


class ParamEditors(QWidget):
    """Fields for rule parameters, built from the type of the value.

    The type comes from the default value: a list of strings gets a comma
    separated field, an integer a spin box, a `bool` a checkbox, a string from a
    fixed set a combo box. There is deliberately no separate type schema: it
    would drift from the parameters themselves on the first edit to
    `qa_rules.py`.
    """

    changed = Signal()

    # parameters whose values are an enumeration rather than free text
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
            "RulesWindow", "Stay silent when a reference is replaced by a "
                           "wrapper: one lost and one added is a swap, not a loss"),
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
        # parameters of the user's own rules
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
            return self._list_editor(value)
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

    # Lists of inflection helpers get long: French Stellaris has 206 of them, CK2
    # 127. That does not fit a comma-separated line, and editing it there is
    # dangerous: one deleted comma glues two names together and both stop working
    # in silence. A long list gets a multi-line field, one name per line, and stays
    # readable.
    LONG_LIST = 12

    def _list_editor(self, value) -> QWidget:
        items = [str(v) for v in value]
        if len(items) <= self.LONG_LIST:
            edit = QLineEdit(", ".join(items))
            edit.editingFinished.connect(self.changed.emit)
            return edit
        box = QPlainTextEdit("\n".join(items))
        box.setMaximumHeight(150)
        box.setPlaceholderText(translate("RulesWindow", "One per line"))
        box.setToolTip(fill(translate("RulesWindow", "Values: %1"), len(items)))
        box.focusOutEvent = self._on_list_blur(box)
        return box

    def _on_list_blur(self, box: QPlainTextEdit):
        """An edit in a long field counts as finished when focus leaves it.

        `QPlainTextEdit` has no `editingFinished`, and emitting on every letter
        would mean rechecking the whole project on each keystroke.
        """
        original = QPlainTextEdit.focusOutEvent

        def handler(event, _box=box):
            original(_box, event)
            self.changed.emit()

        return handler

    def values(self, rule: Rule) -> dict:
        """The field values, coerced to the type of the default parameter."""
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
        if isinstance(widget, QPlainTextEdit):
            # newline or comma alike: the list may have been pasted from anywhere
            parts = widget.toPlainText().replace(",", "\n").split("\n")
            return [p.strip() for p in parts if p.strip()]
        text = widget.text().strip()
        if isinstance(default, (list, tuple)):
            return [p.strip() for p in text.split(",") if p.strip()]
        if isinstance(default, float):
            try:
                return float(text.replace(",", "."))
            except ValueError:
                return default
        return text

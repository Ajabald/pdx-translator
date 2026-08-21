"""The «Preferences» window.

Before it the settings were smeared about: some in the «View» menu, some inside
the task dialogs, while the Bdd/Projects/backups folders and the number of
backups had no interface at all — only registry keys. The «View» menu kept what
is properly its own: the visibility of panels is a view, not a setting.

The rule for the tabs: only what has a live point where it applies gets in here.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFontComboBox,
    QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QStackedWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from pdxloc import settings
from pdxloc.core import mt
from pdxloc.core.i18n import translate
from pdxloc.gui import ask, language, prefs, theme
from pdxloc.gui.widgets import HintLabel


class _PathRow(QWidget):
    """A path field with a «Browse…» button, the same in all three rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.edit = QLineEdit()
        row.addWidget(self.edit, 1)
        button = QToolButton()
        button.setText(translate("Prefs", "Browse…"))
        button.setToolTip(translate("Prefs", "Choose a folder"))
        button.clicked.connect(self._browse)
        row.addWidget(button)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("Prefs", "Choose a folder"), self.edit.text())
        if path:
            self.edit.setText(path)

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, path) -> None:
        self.edit.setText(str(path))


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Prefs", "Preferences"))
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), translate("Prefs", "General"))
        tabs.addTab(self._folders_tab(), translate("Prefs", "Folders"))
        tabs.addTab(self._editor_tab(), translate("Prefs", "Editor"))
        tabs.addTab(self._memory_tab(), translate("Prefs", "Memory"))
        tabs.addTab(self._mt_tab(), translate("Prefs", "Machine translation"))
        layout.addWidget(tabs, 1)

        box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(box)

        self.load()

    # --- tabs ---

    def _general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.language_combo = QComboBox()
        for code, label in language.available().items():
            self.language_combo.addItem(label, code)
        form.addRow(translate("Prefs", "Interface language:"), self.language_combo)
        self.theme_combo = QComboBox()
        for name, label in theme.THEME_LABELS.items():
            self.theme_combo.addItem(label, name)
        form.addRow(translate("Prefs", "Colour theme:"), self.theme_combo)
        self.reopen_last = QCheckBox(translate("Prefs", "Open the last project on startup"))
        form.addRow(self.reopen_last)
        # The only way back from «do not ask again»: a reminder can be silenced from
        # inside itself, but brought back only from here. A setting that cannot be
        # undone is a trap.
        self.unmute_reminders = QCheckBox(
            translate("Prefs", "Show hidden reminders again"))
        form.addRow(self.unmute_reminders)
        form.addRow(HintLabel(
            translate("Prefs",
                      "The interface language applies immediately. It is not "
                      "related to the translation languages — those are set in "
                      "the project itself.")))
        return page

    def _folders_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.bdd_row = _PathRow()
        self.projects_row = _PathRow()
        self.backups_row = _PathRow()
        form.addRow(translate("Prefs", "Translation memory databases:"), self.bdd_row)
        form.addRow(translate("Prefs", "Projects:"), self.projects_row)
        form.addRow(translate("Prefs", "Backups:"), self.backups_row)
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(0, 50)
        self.backup_keep.setToolTip(
            translate("Prefs",
                      "Snapshots of files overwritten when writing the "
                      "translation to the mod.\n0 — do not keep any."))
        form.addRow(translate("Prefs", "Keep copies per project:"), self.backup_keep)
        form.addRow(HintLabel(
            translate("Prefs",
                      "Copies must not be put next to the localization: the game "
                      "reads every *.yml from that folder and would load a backup "
                      "file as if it were a real one.")))
        return page

    def _editor_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.font_family = QFontComboBox()
        self.font_family.setFontFilters(QFontComboBox.MonospacedFonts)
        form.addRow(translate("Prefs", "Font of the original and translation fields:"),
                    self.font_family)
        self.font_size = QSpinBox()
        self.font_size.setRange(7, 24)
        form.addRow(translate("Prefs", "Font size:"), self.font_size)
        self.row_height = QSpinBox()
        self.row_height.setRange(16, 48)
        form.addRow(translate("Prefs", "Table row height:"), self.row_height)
        self.cell_limit = QSpinBox()
        self.cell_limit.setRange(40, 1000)
        self.cell_limit.setSingleStep(10)
        self.cell_limit.setToolTip(
            translate("Prefs",
                      "Long rows are truncated in the cell — the full text is "
                      "always visible in the editor pane and in the tooltip"))
        form.addRow(translate("Prefs", "Truncate cell text after, characters:"),
                    self.cell_limit)
        self.show_grid = QCheckBox(translate("Prefs", "Show the table grid"))
        form.addRow(self.show_grid)
        self.highlight_changes = QCheckBox(translate("Prefs", "Highlight changes of the original"))
        form.addRow(self.highlight_changes)
        return page

    def _memory_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.min_score = QSpinBox()
        self.min_score.setRange(30, 99)
        self.min_score.setSuffix(" %")
        self.min_score.setToolTip(
            translate("Prefs",
                      "Below this similarity, similar rows do not appear in "
                      "the suggestions"))
        form.addRow(translate("Prefs", "Suggestion similarity threshold:"),
                    self.min_score)
        self.suggestions = QSpinBox()
        self.suggestions.setRange(1, 50)
        form.addRow(translate("Prefs", "Suggestions to show:"), self.suggestions)
        form.addRow(HintLabel(
            translate("Prefs",
                      "Exact matches are always shown and come first — the "
                      "threshold applies to similar rows only.")))
        return page

    def _mt_tab(self) -> QWidget:
        """Machine translation: the provider, the key and the bounds of a run.

        The provider panels live in a stack rather than side by side: for DeepL
        it is a choice between Free and Pro, for the LLM ones a model and wishes
        about the translation, for Yandex a folder id as well. Shown all at once
        they would hang there dead three quarters of the time.
        """
        page = QWidget()
        box = QVBoxLayout(page)
        form = QFormLayout()
        box.addLayout(form)

        self.mt_provider = QComboBox()
        for name, label in mt.provider_labels().items():
            self.mt_provider.addItem(translate("Mt", label), name)
        self.mt_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(translate("Prefs", "Service:"), self.mt_provider)

        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        self.mt_key = QLineEdit()
        self.mt_key.setEchoMode(QLineEdit.Password)
        key_row.addWidget(self.mt_key, 1)
        self.mt_key_show = QToolButton()
        self.mt_key_show.setText(translate("Prefs", "Show"))
        self.mt_key_show.setCheckable(True)
        self.mt_key_show.toggled.connect(self._on_key_visibility)
        key_row.addWidget(self.mt_key_show)
        self.mt_key_check = QPushButton(translate("Prefs", "Check"))
        self.mt_key_check.clicked.connect(self._check_key)
        key_row.addWidget(self.mt_key_check)
        key_holder = QWidget()
        key_holder.setLayout(key_row)
        form.addRow(translate("Prefs", "Access key:"), key_holder)

        self.mt_key_state = HintLabel("")
        form.addRow(self.mt_key_state)

        # --- the panels that depend on the provider ---
        self.mt_panels = QStackedWidget()
        self.mt_deepl_pro = QCheckBox(
            translate("Prefs", "Pro subscription (a different address, not a tariff)"))
        self.mt_llm_model = QLineEdit()
        self.mt_llm_model.setPlaceholderText(
            translate("Prefs", "the service default"))
        self.mt_llm_prompt = QPlainTextEdit()
        self.mt_llm_prompt.setPlaceholderText(translate(
            "Prefs", "For example: formal tone, «you» in the plural, "
                     "keep the names as in the glossary"))
        self.mt_llm_prompt.setFixedHeight(60)
        self.mt_yandex_folder = QLineEdit()

        self.mt_panels.addWidget(QWidget())                     # 0 means nothing
        self.mt_panels.addWidget(self._panel({"": self.mt_deepl_pro}))
        self.mt_panels.addWidget(self._panel({
            translate("Prefs", "Model:"): self.mt_llm_model,
            translate("Prefs", "Extra instructions:"): self.mt_llm_prompt}))
        self.mt_panels.addWidget(self._panel({
            translate("Prefs", "Folder id:"): self.mt_yandex_folder}))
        box.addWidget(self.mt_panels)

        limits = QFormLayout()
        self.mt_budget = QSpinBox()
        self.mt_budget.setRange(200, 100_000)
        self.mt_budget.setSingleStep(500)
        self.mt_budget.setToolTip(translate(
            "Prefs", "How many characters go into one request. Rows are never "
                     "cut in half: one that does not fit is left untranslated"))
        limits.addRow(translate("Prefs", "Characters per request:"), self.mt_budget)
        self.mt_throttle = QSpinBox()
        self.mt_throttle.setRange(0, 5000)
        self.mt_throttle.setSingleStep(50)
        self.mt_throttle.setSuffix(" ms")
        self.mt_throttle.setToolTip(translate(
            "Prefs", "A pause between requests. Without it services start "
                     "refusing halfway through a long run"))
        limits.addRow(translate("Prefs", "Pause between requests:"), self.mt_throttle)
        self.mt_retries = QSpinBox()
        self.mt_retries.setRange(0, 10)
        limits.addRow(translate("Prefs", "Retries after a refusal:"), self.mt_retries)
        self.mt_timeout = QSpinBox()
        self.mt_timeout.setRange(5, 300)
        self.mt_timeout.setSuffix(" s")
        limits.addRow(translate("Prefs", "Request timeout:"), self.mt_timeout)
        box.addLayout(limits)

        box.addWidget(HintLabel(translate(
            "Prefs",
            "Machine translation is written with the «Machine (unchecked)» "
            "status. It does not go into the translation memory and is not "
            "written to the mod until you allow it in the export window.")))
        box.addStretch(1)
        return page

    @staticmethod
    def _panel(rows: dict) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        for label, widget in rows.items():
            form.addRow(label, widget) if label else form.addRow(widget)
        return page

    # --- behaviour of the machine translation tab ---

    _PANEL_BY_PROVIDER = {"deepl": 1, "claude": 2, "openai": 2, "yandex": 3}

    def _on_provider_changed(self) -> None:
        name = self.mt_provider.currentData() or "none"
        self.mt_panels.setCurrentIndex(self._PANEL_BY_PROVIDER.get(name, 0))
        # Whether a service asks for a key is its own business: the stub and the manual
        # route have none, and with them an input field is a promise with nothing to
        # do.
        provider = mt.PROVIDERS.get(name)
        needs_key = bool(getattr(provider, "needs_key", False))
        for widget in (self.mt_key, self.mt_key_show, self.mt_key_check):
            widget.setEnabled(needs_key)
        self.mt_key.setText(mt.api_key(name) if needs_key else "")
        self._show_key_state(name if needs_key else "none")

    def _on_key_visibility(self, shown: bool) -> None:
        self.mt_key.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)

    def _show_key_state(self, name: str) -> None:
        """Tell the truth about how the key is stored.

        A silent fallback to plain text would teach people to consider an
        unprotected key protected, so both halves are named outright.
        """
        if name == "none" or not self.mt_key.text():
            self.mt_key_state.setText("")
            return
        if mt.key_is_protected(name):
            self.mt_key_state.setText(translate(
                "Prefs", "The key is protected by Windows for your account. "
                         "It is unreadable from another account, but a program "
                         "running as you can read it."))
        else:
            self.mt_key_state.setText(translate(
                "Prefs", "The key is stored as plain text: this system cannot "
                         "protect it."))

    def _check_key(self) -> None:
        """One cheap request: does the service accept the key."""
        from pdxloc.gui import mt_worker

        name = self.mt_provider.currentData() or "none"
        self.mt_key_check.setEnabled(False)
        self.mt_key_state.setText(translate("Prefs", "Checking…"))
        self._key_worker = mt_worker.KeyCheckWorker(
            name, self._provider_config(), "en", "ru")
        self._key_worker.finished.connect(self._on_key_checked)
        self._key_thread = mt_worker.start(self._key_worker, self)
        self._key_worker.finished.connect(self._key_thread.quit)
        self._key_thread.start()

    def _on_key_checked(self, ok: bool, message: str) -> None:
        self.mt_key_check.setEnabled(True)
        self.mt_key_state.setText(message)

    def _provider_config(self) -> mt.ProviderConfig:
        return mt.ProviderConfig(
            api_key=self.mt_key.text().strip(),
            pro=self.mt_deepl_pro.isChecked(),
            model=self.mt_llm_model.text().strip(),
            prompt=self.mt_llm_prompt.toPlainText().strip(),
            extra={"folder_id": self.mt_yandex_folder.text().strip()},
            timeout=float(self.mt_timeout.value()),
        )

    # --- values ---

    def load(self) -> None:
        """Show the current values.

        We read but write nothing: otherwise merely opening the window — from a
        test, among other things — would litter the user's settings.
        """
        self.language_combo.setCurrentIndex(
            max(self.language_combo.findData(language.current()), 0))
        self.theme_combo.setCurrentIndex(
            max(self.theme_combo.findData(theme.current()), 0))
        self.reopen_last.setChecked(prefs.get("general/reopen_last"))
        self._load_reminders()

        self.bdd_row.set_value(settings.bdd_dir())
        self.projects_row.set_value(settings.projects_dir())
        self.backups_row.set_value(settings.backups_dir())
        self.backup_keep.setValue(settings.backup_keep())

        self.font_family.setCurrentFont(QFont(prefs.get("editor/font_family")))
        self.font_size.setValue(prefs.get("editor/font_size"))
        self.row_height.setValue(prefs.get("editor/row_height"))
        self.cell_limit.setValue(prefs.get("editor/cell_limit"))
        self.show_grid.setChecked(prefs.get("editor/show_grid"))
        self.highlight_changes.setChecked(prefs.get("detail/highlight_changes"))

        self.min_score.setValue(prefs.get("tm/min_score"))
        self.suggestions.setValue(prefs.get("tm/suggestions"))

        self.mt_deepl_pro.setChecked(prefs.get("mt/deepl_pro"))
        self.mt_llm_model.setText(prefs.get("mt/llm_model"))
        self.mt_llm_prompt.setPlainText(prefs.get("mt/llm_prompt"))
        self.mt_yandex_folder.setText(prefs.get("mt/yandex_folder"))
        self.mt_budget.setValue(prefs.get("mt/char_budget"))
        self.mt_throttle.setValue(prefs.get("mt/throttle_ms"))
        self.mt_retries.setValue(prefs.get("mt/retries"))
        self.mt_timeout.setValue(prefs.get("mt/timeout_sec"))
        # the provider goes last: it pulls in the key and its own panel
        self.mt_provider.setCurrentIndex(
            max(self.mt_provider.findData(prefs.get("mt/provider")), 0))
        self._on_provider_changed()

    def _load_reminders(self) -> None:
        """The box is alive only while there is something to bring back.

        Otherwise it would promise an action with nothing to act on — exactly the
        dead checkbox that must not be here. The tooltip meanwhile explains why
        it is greyed out: a disabled control with no explanation reads as
        breakage.
        """
        muted = ask.any_muted()
        self.unmute_reminders.setChecked(False)
        self.unmute_reminders.setEnabled(muted)
        self.unmute_reminders.setToolTip(
            translate("Prefs",
                      "Reminders you switched off with «Do not ask again»")
            if muted else
            translate("Prefs", "No reminders are hidden right now"))

    def apply(self) -> None:
        prefs.set("general/reopen_last", self.reopen_last.isChecked())
        if self.unmute_reminders.isChecked():
            ask.unmute_all()
            self._load_reminders()

        for row, setter in ((self.bdd_row, settings.set_bdd_dir),
                            (self.projects_row, settings.set_projects_dir),
                            (self.backups_row, settings.set_backups_dir)):
            if row.value():
                setter(Path(row.value()))
        prefs.set("backup/keep", self.backup_keep.value())

        prefs.set("editor/font_family", self.font_family.currentFont().family())
        prefs.set("editor/font_size", self.font_size.value())
        prefs.set("editor/row_height", self.row_height.value())
        prefs.set("editor/cell_limit", self.cell_limit.value())
        prefs.set("editor/show_grid", self.show_grid.isChecked())
        prefs.set("detail/highlight_changes", self.highlight_changes.isChecked())

        prefs.set("tm/min_score", self.min_score.value())
        prefs.set("tm/suggestions", self.suggestions.value())

        provider = self.mt_provider.currentData() or "none"
        prefs.set("mt/provider", provider)
        prefs.set("mt/deepl_pro", self.mt_deepl_pro.isChecked())
        prefs.set("mt/llm_model", self.mt_llm_model.text().strip())
        prefs.set("mt/llm_prompt", self.mt_llm_prompt.toPlainText().strip())
        prefs.set("mt/yandex_folder", self.mt_yandex_folder.text().strip())
        prefs.set("mt/char_budget", self.mt_budget.value())
        prefs.set("mt/throttle_ms", self.mt_throttle.value())
        prefs.set("mt/retries", self.mt_retries.value())
        prefs.set("mt/timeout_sec", self.mt_timeout.value())
        # The key goes past prefs: it is protected and stored per provider, and nobody
        # needs a «setting changed» signal on every edit of it.
        if provider != "none":
            mt.save_api_key(provider, self.mt_key.text())
            self._show_key_state(provider)

        # The language and the theme go last: both repaint the windows, and that is
        # worth doing with the font and the row height already applied. Language before
        # theme: it changes the length of the labels, while the theme changes only
        # colours.
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        code = self.language_combo.currentData()
        if code and code != language.current():
            language.apply(app, code)

        name = self.theme_combo.currentData()
        if name != theme.current():
            theme.apply_theme(app, name)

    def _accept(self) -> None:
        self.apply()
        self.accept()

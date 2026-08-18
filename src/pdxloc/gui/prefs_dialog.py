"""Окно «Параметры».

До него настройки были размазаны: часть в меню «Вид», часть внутри диалогов
задач, а папки Bdd/Projects/backups и число резервных копий вообще не имели
интерфейса — только ключи реестра. Меню «Вид» осталось при своём: видимость
панелей — это вид, а не настройка.

Правило вкладок: сюда попадает только то, у чего есть живая точка применения.
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
    """Поле пути с кнопкой «Обзор…» — одинаковое во всех трёх строках."""

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

    # --- вкладки ---

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
        # Единственный путь назад для «больше не спрашивать»: заглушить
        # напоминание можно из него самого, а вернуть — только отсюда.
        # Настройка, которую невозможно отменить, — ловушка.
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
        """Машинный перевод: провайдер, ключ и рамки прогона.

        Панели провайдеров лежат в стопке, а не рядом: у DeepL это выбор между
        Free и Pro, у LLM — модель и пожелания к переводу, у Yandex — ещё и
        идентификатор каталога. Показанные разом, они висели бы мёртвыми
        три четверти времени.
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

        # --- панели, зависящие от провайдера ---
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

        self.mt_panels.addWidget(QWidget())                     # 0 — ничего
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

    # --- поведение вкладки машинного перевода ---

    _PANEL_BY_PROVIDER = {"deepl": 1, "claude": 2, "openai": 2, "yandex": 3}

    def _on_provider_changed(self) -> None:
        name = self.mt_provider.currentData() or "none"
        self.mt_panels.setCurrentIndex(self._PANEL_BY_PROVIDER.get(name, 0))
        # Спрашивает ли сервис ключ, знает он сам: у заглушки и ручного режима
        # ключа нет, и поле ввода при них — обещание, которому нечего делать.
        provider = mt.PROVIDERS.get(name)
        needs_key = bool(getattr(provider, "needs_key", False))
        for widget in (self.mt_key, self.mt_key_show, self.mt_key_check):
            widget.setEnabled(needs_key)
        self.mt_key.setText(mt.api_key(name) if needs_key else "")
        self._show_key_state(name if needs_key else "none")

    def _on_key_visibility(self, shown: bool) -> None:
        self.mt_key.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)

    def _show_key_state(self, name: str) -> None:
        """Сказать правду о том, как лежит ключ.

        Молчаливый откат к открытому тексту научил бы считать незащищённый
        ключ защищённым, поэтому обе половины названы прямо.
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
        """Один дешёвый запрос — принимает ли сервис ключ."""
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

    # --- значения ---

    def load(self) -> None:
        """Показать текущие значения.

        Читаем, но ничего не пишем: иначе простое открытие окна (в том числе из
        теста) засоряло бы настройки пользователя.
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
        # провайдера ставим последним: он подтягивает ключ и панель под себя
        self.mt_provider.setCurrentIndex(
            max(self.mt_provider.findData(prefs.get("mt/provider")), 0))
        self._on_provider_changed()

    def _load_reminders(self) -> None:
        """Галка живёт, только пока есть что возвращать.

        Иначе она обещала бы действие, которому не над чем сработать, — а это
        ровно та мёртвая галка, которой здесь быть не должно. Подсказка при
        этом объясняет, почему она погашена: погашенный элемент без объяснения
        читается как поломка.
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
        # Ключ идёт мимо prefs: он защищается и хранится по провайдеру,
        # а сигнал «настройка изменилась» на каждую его правку не нужен никому.
        if provider != "none":
            mt.save_api_key(provider, self.mt_key.text())
            self._show_key_state(provider)

        # Язык и тема — последними: обе перерисовывают окна, и делать это стоит
        # уже с применёнными шрифтом и высотой строки. Язык вперёд темы: он
        # меняет длину подписей, а тема — только цвета.
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

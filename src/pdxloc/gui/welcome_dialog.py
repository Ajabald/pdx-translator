"""Мастер первого запуска: язык, базы памяти, первый проект.

Раньше новый пользователь получал пустой список проектов и ни одной подсказки.
Два умолчания при этом молча решались за него, и оба неверно: интерфейс
включался на языке системы (а перевод мог быть и не на её языке), а работа
начиналась без единой базы памяти переводов — то есть без половины смысла
инструмента.

Три шага и ни одним больше. Тема и папки остались в «Параметрах»: они меняются
редко и разумно выглядят по умолчанию, а мастер, который спрашивает обо всём,
пролистывают не читая.

Мастер показывается **один раз**. Всё, что он предлагает, доступно и потом
обычными командами, поэтому «Пропустить» здесь — полноправный ответ, а не
уловка.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from pdxloc import project as project_mod
from pdxloc.core.i18n import fill, translate
from pdxloc.gui import language, prefs
from pdxloc.gui.widgets import HintLabel

DONE_KEY = "general/first_run_done"


def needed() -> bool:
    """Показывать ли мастер. Один раз за жизнь установки."""
    return not prefs.get(DONE_KEY)


def mark_done() -> None:
    prefs.set(DONE_KEY, True)


class WelcomeDialog(QDialog):
    """Три шага знакомства. Каждый умеет ничего не делать."""

    buildDatabaseRequested = Signal()
    createProjectRequested = Signal()
    openProjectRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Welcome", "Getting started"))
        self.setMinimumSize(600, 380)
        self._step = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self.heading = QLabel()
        font = self.heading.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.heading.setFont(font)
        layout.addWidget(self.heading)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._language_page())
        self.pages.addWidget(self._databases_page())
        self.pages.addWidget(self._project_page())
        layout.addWidget(self.pages, 1)

        row = QHBoxLayout()
        self.skip_btn = QPushButton(translate("Welcome", "Skip"))
        self.skip_btn.clicked.connect(self._finish)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        self.back_btn = QPushButton(translate("Welcome", "Back"))
        self.back_btn.clicked.connect(lambda: self._go(self._step - 1))
        row.addWidget(self.back_btn)
        self.next_btn = QPushButton(translate("Welcome", "Next"))
        self.next_btn.clicked.connect(self._on_next)
        self.next_btn.setDefault(True)
        row.addWidget(self.next_btn)
        layout.addLayout(row)

        self._go(0)

    # --- шаги ---

    def _language_page(self) -> QWidget:
        """Первым шагом — чтобы остальные читались на понятном языке."""
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        text = QLabel(translate(
            "Welcome",
            "Choose the language of the interface. It can be changed at any "
            "time in «File → Preferences»."))
        text.setWordWrap(True)
        box.addWidget(text)

        row = QHBoxLayout()
        self.language_combo = QComboBox()
        for code, label in language.available().items():
            self.language_combo.addItem(label, code)
        # The language in effect, not the system one. The window is already
        # drawn in whatever apply_saved() picked, so offering a different one
        # makes the wizard contradict itself — Chinese headings above a list
        # that says "Russian". Reachable without any trickery: a hive adopted
        # from the previous application name carries a language over, while
        # first_run_done is absent from the new hive by definition.
        self.language_combo.setCurrentIndex(
            max(self.language_combo.findData(language.current()), 0))
        self.language_combo.currentIndexChanged.connect(self._apply_language)
        row.addWidget(self.language_combo)
        row.addStretch(1)
        box.addLayout(row)
        box.addWidget(HintLabel(translate(
            "Welcome",
            "The interface language has nothing to do with the languages you "
            "translate between — those belong to the project.")))
        box.addStretch(1)
        return page

    def _databases_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        self.db_text = QLabel()
        self.db_text.setWordWrap(True)
        box.addWidget(self.db_text)

        row = QHBoxLayout()
        self.db_btn = QPushButton(translate("Welcome", "Build a database…"))
        self.db_btn.clicked.connect(self._on_build_database)
        row.addWidget(self.db_btn)
        row.addStretch(1)
        box.addLayout(row)
        box.addStretch(1)
        return page

    def _on_build_database(self) -> None:
        """Собрать базу — и перечитать страницу.

        Окно сборки модально, поэтому управление возвращается сюда уже после
        него. Не перечитав текст, мастер оставил бы на экране «баз памяти пока
        нет» сразу после того, как база собрана, — и следующий шаг человек
        проходил бы, не веря ни одному слову.
        """
        self.buildDatabaseRequested.emit()
        self._refresh_databases_page()

    def _project_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        text = QLabel(translate(
            "Welcome",
            "A project holds everything: rows, statuses, translation memory and "
            "the history of the original. It is a single file you can copy or "
            "hand to another person."))
        text.setWordWrap(True)
        box.addWidget(text)

        row = QHBoxLayout()
        create = QPushButton(translate("Welcome", "Create a project…"))
        create.clicked.connect(self.createProjectRequested)
        create.clicked.connect(self.accept)
        row.addWidget(create)
        open_btn = QPushButton(translate("Welcome", "Open a project…"))
        open_btn.clicked.connect(self.openProjectRequested)
        open_btn.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addStretch(1)
        box.addLayout(row)
        box.addStretch(1)
        return page

    # --- навигация ---

    def _refresh_databases_page(self) -> None:
        """Текст шага зависит от того, есть ли базы: врать нельзя ни в одну сторону."""
        found = len(project_mod.all_tm_databases())
        if found:
            self.db_text.setText(fill(translate(
                "Welcome",
                "Translation memory databases found: %1. They fill in strings "
                "the mod copied from the game and prompt you with how similar "
                "lines were translated before."), found))
            self.db_btn.setText(translate("Welcome", "Build one more…"))
        else:
            self.db_text.setText(translate(
                "Welcome",
                "There are no translation memory databases yet. A database "
                "built from your copy of the game fills in strings the mod "
                "copied from it — often hundreds of them — and prompts you "
                "with how similar lines were translated before.\n\n"
                "Building takes seconds and needs nothing but the game "
                "localization folders."))
            self.db_btn.setText(translate("Welcome", "Build a database…"))

    def _go(self, step: int) -> None:
        self._step = max(0, min(step, self.pages.count() - 1))
        self.pages.setCurrentIndex(self._step)
        headings = (
            translate("Welcome", "Interface language"),
            translate("Welcome", "Translation memory"),
            translate("Welcome", "First project"),
        )
        self.heading.setText(headings[self._step])
        if self._step == 1:
            self._refresh_databases_page()
        self.back_btn.setEnabled(self._step > 0)
        self.next_btn.setText(
            translate("Welcome", "Done") if self._step == self.pages.count() - 1
            else translate("Welcome", "Next"))

    def _on_next(self) -> None:
        if self._step == self.pages.count() - 1:
            self._finish()
            return
        self._go(self._step + 1)

    def _apply_language(self) -> None:
        from PySide6.QtWidgets import QApplication

        code = self.language_combo.currentData()
        if code:
            language.apply(QApplication.instance(), code)
        self._retranslate()

    def _retranslate(self) -> None:
        """Мастер живёт дольше смены языка — подписи меняем на месте."""
        self.setWindowTitle(translate("Welcome", "Getting started"))
        self.skip_btn.setText(translate("Welcome", "Skip"))
        self.back_btn.setText(translate("Welcome", "Back"))
        self._go(self._step)

    def _finish(self) -> None:
        mark_done()
        self.accept()

    def done(self, result: int) -> None:
        # Закрыли крестиком — мастер всё равно показан, и второй раз ему
        # взяться неоткуда: иначе он встречал бы при каждом запуске.
        mark_done()
        super().done(result)

"""Окно памяти переводов — единственная точка входа (F9).

Раньше это были три отдельных окна: «Память переводов», «Базы памяти
переводов» и «Создать базу переводов из папок», плюс выгрузка проекта, которая
вообще открывала только файловый диалог. Все четыре занимаются одним и тем же
и постоянно отсылали друг к другу («отключить базу можно в меню
Инструменты → …»). Теперь это вкладки, а состояние активной вкладки живёт в
общей нижней полосе — счётчик уехал от кнопок, к которым не относился.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QTabWidget,
    QVBoxLayout,
)

from pdxloc.core.i18n import translate
from pdxloc.gui.tm_build_tab import TmBuildTab
from pdxloc.gui.tm_entries_tab import TmEntriesTab
from pdxloc.gui.tm_sources_tab import TmSourcesTab


class TmWindow(QDialog):
    """Вкладки памяти переводов. Проект нужен не всем — без него остаётся сборка.

    Мастер первого запуска зовёт это окно **до** того, как заведён хоть один
    проект: первую базу памяти собирают раньше первого перевода. Раньше окно
    этого не переживало — `languages(None)` падал прямо в слоте кнопки, а у
    собранного приложения консоли нет (`console=False` в спеке), поэтому
    трейсбек уходил в никуда и кнопка выглядела мёртвой.
    """

    def __init__(self, conn: sqlite3.Connection | None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("TmWindow", "Translation memory"))
        self.setMinimumSize(1000, 620)

        from pdxloc import project as project_mod

        # Без проекта языки взять неоткуда — берём те же умолчания, что и сама
        # вкладка сборки: папки на ней всё равно указываются руками.
        src_lang, tgt_lang = "english", "russian"
        if conn is not None:
            langs = project_mod.languages(conn)
            src_lang, tgt_lang = langs.src_lang, langs.tgt_lang

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        # «Записи» — собственная память проекта, «Базы» — подключённые к нему.
        # Без проекта обе показывали бы пустоту, объяснить которую нечем, —
        # поэтому их просто нет, а не «есть, но выключены».
        self.entries = TmEntriesTab(conn) if conn is not None else None
        self.sources = TmSourcesTab(conn) if conn is not None else None
        self.build = TmBuildTab(src_lang=src_lang, tgt_lang=tgt_lang, conn=conn)
        if self.entries is not None:
            self.tabs.addTab(self.entries, translate("TmWindow", "Entries"))
        if self.sources is not None:
            self.tabs.addTab(self.sources, translate("TmWindow", "Databases"))
        self.tabs.addTab(self.build, translate("TmWindow", "Build a database"))
        layout.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        bottom.addWidget(box)
        layout.addLayout(bottom)

        for tab in self._tabs():
            tab.statusChanged.connect(self._on_tab_status)
        self.tabs.currentChanged.connect(lambda _: self._show_status())
        # собранная база должна сразу появиться в списке подключаемых
        if self.sources is not None:
            self.build.databasesChanged.connect(self.sources.reload)
        self._show_status()

    def show_build_tab(self) -> None:
        """Открыться сразу на сборке базы — из мастера и из напоминания."""
        self.tabs.setCurrentWidget(self.build)

    def _tabs(self):
        """Только заведённые вкладки: без проекта их одна.

        Через этот же список ходят подписка на `statusChanged` и гашение
        таймеров, поэтому отсутствующую вкладку достаточно не вернуть отсюда.
        """
        return tuple(tab for tab in (self.entries, self.sources, self.build)
                     if tab is not None)

    # --- нижняя полоса ---

    def _on_tab_status(self, text: str) -> None:
        if self.sender() is self.tabs.currentWidget():
            self.status_label.setText(text)

    def _show_status(self) -> None:
        self.status_label.setText(self.tabs.currentWidget().status_text())

    # --- закрытие ---

    def _stop_timers(self) -> None:
        """Отложенные запросы не должны пережить окно.

        Соединение проекта к тому времени бывает уже закрыто, и таймер падал на
        мёртвой базе. Раз вкладок несколько, гасим централизованно.
        """
        for tab in self._tabs():
            tab.shutdown()

    def _confirm_close_while_building(self) -> bool:
        """Не закрываться молча посреди сборки базы.

        В отдельном окне от этого спасала модальность: уйти было некуда. Во
        вкладках пользователь легко переключится на «Записи» и нажмёт
        «Закрыть», не вспомнив, что сборка ещё идёт.
        """
        if not self.build.is_busy():
            return True
        answer = QMessageBox.question(
            self, translate("TmWindow", "Building a database"),
            translate("TmWindow",
                      "The database is still being built. Interrupt it and close "
                      "the window?\n\nAn unfinished database file will not be "
                      "created."))
        if answer != QMessageBox.Yes:
            return False
        self.build.cancel_build()
        return True

    def closeEvent(self, event) -> None:
        if not self._confirm_close_while_building():
            event.ignore()
            return
        self._stop_timers()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        if not self._confirm_close_while_building():
            return
        self._stop_timers()
        super().done(result)

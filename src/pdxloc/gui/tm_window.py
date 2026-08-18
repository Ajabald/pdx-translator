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
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("TmWindow", "Translation memory"))
        self.setMinimumSize(1000, 620)

        from pdxloc import project as project_mod

        langs = project_mod.languages(conn)
        src_lang, tgt_lang = langs.src_lang, langs.tgt_lang

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.entries = TmEntriesTab(conn)
        self.sources = TmSourcesTab(conn)
        self.build = TmBuildTab(src_lang=src_lang, tgt_lang=tgt_lang, conn=conn)
        self.tabs.addTab(self.entries, translate("TmWindow", "Entries"))
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
        self.build.databasesChanged.connect(self.sources.reload)
        self._show_status()

    def show_build_tab(self) -> None:
        """Открыться сразу на сборке базы — из мастера и из напоминания."""
        self.tabs.setCurrentWidget(self.build)

    def _tabs(self):
        return (self.entries, self.sources, self.build)

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

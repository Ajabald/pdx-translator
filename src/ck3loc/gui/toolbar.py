"""Панель инструментов и полоса контекста проекта.

Иконки берутся из стандартного набора стиля Qt: свой набор пришлось бы рисовать
и тащить в сборку, а тема их перекрашивает сама.

Контекст (языки проекта и подключённые базы памяти) висит справа в шапке — как
у ESP/ESM Translator, где игра, кодировка и активная база видны всегда. Раньше
эти сведения приходилось искать по диалогам.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QSizePolicy, QStyle, QToolBar, QToolButton,
    QWidget,
)

from ck3loc import project as project_mod


def icon(widget: QWidget, name: str):
    return widget.style().standardIcon(getattr(QStyle, name))


class ContextBar(QWidget):
    """Языки проекта и подключённые базы памяти — всегда на виду."""

    tmSourcesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn: sqlite3.Connection | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)

        self.langs = QLabel()
        self.langs.setToolTip("Языки проекта: оригинал → перевод")
        layout.addWidget(self.langs)

        self.tm_button = QToolButton()
        self.tm_button.setPopupMode(QToolButton.InstantPopup)
        self.tm_button.setToolTip(
            "Подключённые базы памяти переводов — можно включать и отключать "
            "прямо отсюда")
        self.tm_menu = QMenu(self.tm_button)
        self.tm_button.setMenu(self.tm_menu)
        layout.addWidget(self.tm_button)

        self.set_project(None)

    def set_project(self, conn: sqlite3.Connection | None) -> None:
        self.conn = conn
        self.refresh()

    def refresh(self) -> None:
        self.tm_menu.clear()
        if self.conn is None:
            self.langs.setText("")
            self.tm_button.setText("Базы памяти")
            self.tm_button.setEnabled(False)
            return
        self.tm_button.setEnabled(True)
        row = self.conn.execute(
            "SELECT src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
        if row:
            self.langs.setText(f"{row['src_lang']} → {row['tgt_lang']}")

        enabled = set(project_mod.get_tm_sources(self.conn))
        total = 0
        for path, meta in project_mod.list_tm_databases():
            entries = int(meta.get("entries", 0) or 0)
            act = QAction(f"{meta.get('name') or path.stem}  ({entries} записей)",
                          self.tm_menu)
            act.setCheckable(True)
            act.setChecked(path.name in enabled)
            act.toggled.connect(
                lambda checked, name=path.name: self._toggle(name, checked))
            self.tm_menu.addAction(act)
            if path.name in enabled:
                total += entries
        if self.tm_menu.isEmpty():
            empty = self.tm_menu.addAction("Баз пока нет")
            empty.setEnabled(False)
        self.tm_button.setText(
            f"Базы памяти: {len(enabled)}" + (f" · {total} записей" if total else ""))

    def _toggle(self, name: str, checked: bool) -> None:
        if self.conn is None:
            return
        names = project_mod.get_tm_sources(self.conn)
        if checked and name not in names:
            names.append(name)
        elif not checked and name in names:
            names.remove(name)
        else:
            return
        project_mod.set_tm_sources(self.conn, names)
        project_mod.attach_tm_sources(self.conn, project_mod.project_tm_paths(self.conn))
        self.refresh()
        self.tmSourcesChanged.emit()


def build_toolbar(window) -> QToolBar:
    """Собрать панель из действий главного окна и экрана редактора."""
    bar = QToolBar("Панель инструментов", window)
    bar.setObjectName("main_toolbar")     # без имени Qt не сохранит состояние
    bar.setToolButtonStyle(bar.toolButtonStyle())

    def add(action: QAction, icon_name: str) -> None:
        action.setIcon(icon(bar, icon_name))
        bar.addAction(action)

    add(window.act_scan, "SP_BrowserReload")
    add(window.act_export, "SP_DialogSaveButton")
    bar.addSeparator()
    add(window.act_find, "SP_FileDialogContentsView")
    add(window.act_tm_manager, "SP_FileDialogDetailedView")
    add(window.act_qa, "SP_DialogApplyButton")
    bar.addSeparator()
    add(window.act_next_untranslated, "SP_MediaSkipForward")
    add(window.act_validate, "SP_DialogYesButton")
    add(window.act_unvalidate, "SP_DialogNoButton")

    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    bar.addWidget(spacer)
    bar.addWidget(window.context_bar)
    return bar

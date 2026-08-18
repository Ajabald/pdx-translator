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

from pdxloc import project as project_mod
from pdxloc.core import games
from pdxloc.core.i18n import translate
from pdxloc.gui import actions as actions_mod
from pdxloc.gui.icons import icon as action_icon

CTX = "Toolbar"


def icon(widget: QWidget, name: str):
    """Стандартная иконка стиля Qt — для мест, где своей ещё нет."""
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
        layout.addWidget(self.langs)

        self.tm_button = QToolButton()
        self.tm_button.setPopupMode(QToolButton.InstantPopup)
        self.tm_menu = QMenu(self.tm_button)
        self.tm_button.setMenu(self.tm_menu)
        layout.addWidget(self.tm_button)

        self.retranslate()
        self.set_project(None)

    def retranslate(self) -> None:
        """Полоса контекста собирается заново — подписи в ней динамические."""
        self.langs.setToolTip(translate("Toolbar", "Project languages: original → translation"))
        self.tm_button.setToolTip(translate(
            "Toolbar", "Attached translation memory databases — they can be "
                       "switched on and off right here"))
        self.refresh()

    def set_project(self, conn: sqlite3.Connection | None) -> None:
        self.conn = conn
        self.refresh()

    def refresh(self) -> None:
        self.tm_menu.clear()
        if self.conn is None:
            self.langs.setText("")
            self.tm_button.setText(translate("Toolbar", "Memory databases"))
            self.tm_button.setEnabled(False)
            return
        self.tm_button.setEnabled(True)
        langs = project_mod.languages(self.conn)
        pair = f"{langs.src_lang} → {langs.tgt_lang}"
        if langs.split:
            # языки текста расходятся с папками — показываем оба, иначе
            # шапка врала бы о том, на каком языке идёт перевод
            pair += f"  ({langs.src_locale} → {langs.tgt_locale})"
        # Игра впереди языков, как в EET, где она видна всегда: у человека с
        # проектами двух игр иначе нет способа заметить, что он правит не тот.
        self.langs.setText(f"{games.title(project_mod.game(self.conn))} · {pair}")

        enabled = set(project_mod.get_tm_sources(self.conn))
        entries_word = translate("Toolbar", "entries")
        total = 0
        for path, meta in project_mod.list_tm_databases(
                game=project_mod.game(self.conn)):
            entries = int(meta.get("entries", 0) or 0)
            act = QAction(f"{meta.get('name') or path.stem}  "
                          f"({entries} {entries_word})",
                          self.tm_menu)
            act.setCheckable(True)
            act.setChecked(path.name in enabled)
            act.toggled.connect(
                lambda checked, name=path.name: self._toggle(name, checked))
            self.tm_menu.addAction(act)
            if path.name in enabled:
                total += entries
        if self.tm_menu.isEmpty():
            empty = self.tm_menu.addAction(translate("Toolbar", "No databases yet"))
            empty.setEnabled(False)
        suffix = f" · {total} {entries_word}" if total else ""
        label = translate("Toolbar", "Memory databases")
        self.tm_button.setText(f"{label}: {len(enabled)}{suffix}")

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


def build_toolbar(window, registry) -> QToolBar:
    """Собрать панель из действий реестра.

    Панель — витрина, а не отдельный набор команд: каждая кнопка обязана иметь
    пункт главного меню (см. `actions.TOOLBAR` и тест, который это стережёт).
    Раньше четыре кнопки не имели пункта меню вообще, а две вдобавок были
    самостоятельными QAction-дублями действий таблицы.
    """
    bar = QToolBar(translate("Toolbar", "Toolbar"), window)
    bar.setObjectName("main_toolbar")     # без имени Qt не сохранит состояние

    for spec in actions_mod.ACTIONS:
        if spec.icon:
            glyph = action_icon(bar, spec.icon)
            if glyph is not None:
                registry[spec.id].setIcon(glyph)

    registry.fill_toolbar(bar, actions_mod.TOOLBAR)

    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    bar.addWidget(spacer)
    bar.addWidget(window.context_bar)
    return bar

"""The icons of the actions: our own SVG, recolouring for the theme, soft degradation."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from pdxloc.gui import actions, icons, theme  # noqa: E402

SIZE = QSize(16, 16)


def declared_icons() -> list[str]:
    return sorted({a.icon for a in actions.ACTIONS if a.icon})


@pytest.fixture
def widget(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    return w


def test_the_application_has_its_own_icon(qtbot) -> None:
    """The icon of the window and of the taskbar is not the same as the icon of the exe.

    `icon=` in `pdx-translator.spec` sets the icon of the **file**; the window
    takes the standard Qt icon until `setWindowIcon` says otherwise. From the
    sources there is no exe at all, and without this file the window is always
    nameless.

    `qtbot` is needed not by a widget but by `QIcon` itself: without a QApplication
    Qt brings the process down silently, without a single line in the report.
    """
    icon = icons.app_icon()
    assert not icon.isNull(), "нет gui/icons/app.png — соберите tools/make_icon.py"
    assert icon.availableSizes(), "иконка пустая"


def test_every_declared_icon_has_a_file() -> None:
    """The spec promises an icon — the file is obliged to exist, otherwise the button is empty."""
    missing = [name for name in declared_icons() if not icons.available(name)]
    assert not missing, f"нет файлов иконок: {missing}"


@pytest.mark.parametrize("name", declared_icons())
def test_icon_draws_something(name: str, widget) -> None:
    """An empty pixmap looks like a missing button, not like an error."""
    glyph = icons.icon(widget, name)
    pixmap = glyph.pixmap(SIZE)
    assert not pixmap.isNull()
    image = pixmap.toImage()
    painted = sum(
        1 for y in range(image.height()) for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted > 4, f"иконка {name} почти пустая"


def test_icon_follows_the_theme(widget) -> None:
    """That is what our own QIconEngine was set up for: a QIcon inside a QAction is a
    value, and resetting it in every place would have to be done by hand."""
    glyph = icons.icon(widget, "validate")
    light = glyph.pixmap(SIZE).toImage()
    theme.apply_theme(None, theme.DARK, save=False)
    try:
        dark = glyph.pixmap(SIZE).toImage()
        assert light != dark, "иконка не перекрасилась вместе с темой"
    finally:
        theme.apply_theme(None, theme.LIGHT, save=False)


def test_unknown_name_falls_back_to_the_qt_style(widget) -> None:
    """While there is no icon of our own, a button takes the standard one — the set can
    be drawn one by one without breaking anything."""
    assert not icons.available("нет-такой-иконки")
    assert icons.icon(widget, "scan") is not None
    icons.STANDARD_FALLBACK["выдуманное"] = "SP_FileIcon"
    try:
        assert isinstance(icons.icon(widget, "выдуманное"), QIcon)
    finally:
        del icons.STANDARD_FALLBACK["выдуманное"]


def test_no_icon_name_means_no_icon(widget) -> None:
    assert icons.icon(widget, None) is None


def test_toolbar_buttons_all_carry_an_icon(qtbot, tmp_path, monkeypatch) -> None:
    """A toolbar button without an icon is an empty spot there is nothing to recognise by."""
    from pdxloc import settings

    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    naked = [a.text() for a in win.toolbar.actions()
             if not a.isSeparator() and a.text() and a.icon().isNull()]
    assert not naked, f"кнопки без иконки: {naked}"

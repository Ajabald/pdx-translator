"""Action icons: monochrome SVG, repainted to match the theme.

The toolbar buttons used to take icons from the Qt style, and half of them meant
the wrong thing: a floppy disk stood for «write the translation to the mod», a
«detailed folder view» for «translation memory». You could not recognise a button
at a glance.

The repainting is done by a `QIconEngine` of our own rather than by reinstalling
`QIcon` when the theme changes: a `QIcon` inside a `QAction` is a value, Qt never
asks for it again, and we would have to visit every place an icon has settled —
toolbar, menu, context menu — without missing one. The engine takes the colour at
paint time instead.

`QSvgRenderer` is used directly rather than `QIcon("file.svg")`: that way the
build needs no `qsvg`/`qsvgicon` plugins.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from pdxloc.gui import theme

# While a file is missing the button takes the standard style icon, as it used
# to. That means the set can be drawn one icon at a time without breaking
# anything.
STANDARD_FALLBACK = {
    "scan": "SP_BrowserReload",
    "export": "SP_DialogSaveButton",
    "import": "SP_ArrowDown",
    "find": "SP_FileDialogContentsView",
    "issues": "SP_MessageBoxWarning",
    "filter-reset": "SP_DialogResetButton",
    "from-tm": "SP_ArrowForward",
    "ru-eq-en": "SP_FileDialogBack",
    "validate": "SP_DialogYesButton",
    "unvalidate": "SP_DialogNoButton",
    "custom": "SP_FileDialogDetailedView",
    "ignore": "SP_DialogCancelButton",
    "next-untranslated": "SP_MediaSkipForward",
    "qa": "SP_DialogApplyButton",
    "tm": "SP_FileDialogContentsView",
    "concordance": "SP_FileDialogInfoView",
    "folder": "SP_DirOpenIcon",
    "open": "SP_DirOpenIcon",
    "projects": "SP_FileDialogListView",
    "prefs": "SP_FileDialogDetailedView",
    "undo": "SP_ArrowBack",
    "copy": "SP_FileIcon",
    "paste": "SP_FileIcon",
    "reset": "SP_DialogResetButton",
}


def _icon_dir():
    # importlib.resources rather than Path(__file__): the path is then right both
    # in the sources and inside a PyInstaller onedir build
    return resources.files("pdxloc.gui") / "icons"


def app_icon() -> QIcon:
    """The application's own icon — window, taskbar, Alt+Tab.

    Kept apart from the action icons and never repainted: those are monochrome
    and live by the theme colour, while this one is in colour and there is one
    per application.

    Setting it is mandatory: `icon=` in `pdx-translator.spec` gives the icon of
    the exe **file**, while the window takes the default Qt icon until told
    otherwise. Run from source there is no exe at all, and without this the
    window is forever nameless.
    """
    try:
        path = _icon_dir() / "app.png"
        if path.is_file():
            return QIcon(str(path))
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return QIcon()      # no file: the old behaviour, a standard icon


def available(name: str) -> bool:
    try:
        return (_icon_dir() / f"{name}.svg").is_file()
    except (FileNotFoundError, ModuleNotFoundError):
        return False


@lru_cache(maxsize=64)
def _renderer(name: str) -> QSvgRenderer:
    data = (_icon_dir() / f"{name}.svg").read_bytes()
    return QSvgRenderer(data)


@lru_cache(maxsize=512)
def _tinted(name: str, color: str, width: int, height: int) -> QPixmap:
    """The SVG silhouette, filled with the theme colour.

    Filled through SourceIn rather than by swapping the colour inside the SVG
    text: that does not depend on what paint the icon was drawn with, and it
    keeps the antialiasing.
    """
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    _renderer(name).render(painter, QRectF(0, 0, width, height))
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


def _clear_cache() -> None:
    _tinted.cache_clear()


theme.notifier.changed.connect(_clear_cache)


class _ThemedIconEngine(QIconEngine):
    """The icon takes its colour from the theme at paint time."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        key = "hint" if mode == QIcon.Disabled else "text"
        width = max(1, size.width())
        height = max(1, size.height())
        return _tinted(self.name, theme.color(key), width, height)

    def paint(self, painter: QPainter, rect, mode, state) -> None:
        painter.drawPixmap(rect, self.pixmap(rect.size(), mode, state))

    def actualSize(self, size: QSize, mode, state) -> QSize:
        return size

    def clone(self) -> QIconEngine:
        return _ThemedIconEngine(self.name)


def icon(widget, name: str | None) -> QIcon | None:
    """Иконка действия по имени из спеки; None — если рисовать нечего."""
    if not name:
        return None
    if available(name):
        return QIcon(_ThemedIconEngine(name))
    standard = STANDARD_FALLBACK.get(name)
    if standard is None:
        return None
    style = widget.style()
    return style.standardIcon(getattr(style.StandardPixmap, standard))

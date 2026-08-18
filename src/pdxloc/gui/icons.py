"""Иконки действий: монохромные SVG, перекрашиваемые под тему.

Раньше кнопки панели брали иконки из стиля Qt, и половина по смыслу не
подходила: дискета означала «записать перевод в мод», «детальный вид папки» —
«память переводов». Узнать кнопку с одного взгляда было нельзя.

Перекраска сделана своим `QIconEngine`, а не переустановкой `QIcon` при смене
темы: `QIcon` внутри `QAction` — значение, Qt не переспросит его заново, и
пришлось бы обходить все места, где иконка успела осесть (панель, меню,
контекстное меню), не забыв ни одного. Движок же берёт цвет в момент отрисовки.

`QSvgRenderer` используется напрямую, а не `QIcon("файл.svg")`, — тогда в сборку
не нужны плагины `qsvg`/`qsvgicon`.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from pdxloc.gui import theme

# Пока файла нет, кнопка берёт стандартную иконку стиля — как было раньше.
# Значит набор можно рисовать по одной иконке, ничего не ломая.
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
    # importlib.resources, а не Path(__file__): так путь верен и в исходниках,
    # и внутри onedir-сборки PyInstaller
    return resources.files("pdxloc.gui") / "icons"


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
    """Силуэт SVG, залитый цветом темы.

    Заливка через SourceIn, а не подмена цвета в тексте SVG: не зависит от
    того, какой краской иконка нарисована, и сохраняет сглаживание.
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
    """Иконка берёт цвет из темы в момент отрисовки."""

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

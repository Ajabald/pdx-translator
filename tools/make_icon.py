"""Сборка `pdx-translator.ico` из `tools/appicon.svg`.

    .venv\\Scripts\\python.exe tools\\make_icon.py

Новых зависимостей не заводит: рисует Qt (`QtSvg` уже в PySide6), а контейнер
ICO складывается здесь руками — писать многоразмерный ICO `QImageWriter` не
умеет, он кладёт одну картинку.

Размеры взяты те, что Windows действительно спрашивает: 16 — панель задач и
заголовок окна, 32 — рабочий стол, 48 — «крупные значки», 256 — «огромные» и
предпросмотр в проводнике. Промежуточные 64 и 128 добавлены, чтобы система не
масштабировала 256 вниз в «плитку».

Данные кладём в PNG, а не BMP: Vista и новее это понимают, а файл выходит втрое
меньше — 256×256 в BMP занял бы 256 КБ на один размер.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "tools" / "appicon.svg"
SVG_SMALL = ROOT / "tools" / "appicon-small.svg"
# Ниже этого размера берём упрощённый рисунок: столбцы на такой сетке
# сливаются в серую точку, и грубый знак читается лучше подробного.
SMALL_UPTO = 32
ICO = ROOT / "pdx-translator.ico"
PREVIEW = ROOT / "tools" / "appicon-preview.png"
# Копия внутри пакета: `.ico` в спеке задаёт иконку САМОГО exe, а иконку
# окна и панели задач ставит `QApplication.setWindowIcon`, и ей нужен файл,
# доезжающий и до сборки, и до запуска из исходников.
APP_PNG = ROOT / "src" / "pdxloc" / "gui" / "icons" / "app.png"

SIZES = (16, 32, 48, 64, 128, 256)


def render(size: int) -> bytes:
    """PNG нужного размера из SVG — подробного или упрощённого."""
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    source = SVG_SMALL if size <= SMALL_UPTO else SVG
    QSvgRenderer(str(source)).render(painter)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def build_ico(pngs: dict[int, bytes]) -> bytes:
    """Контейнер ICO: заголовок, таблица записей, следом сами PNG."""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)      # reserved, type=icon, count
    offset = 6 + 16 * count
    entries, blobs = [], []
    for size, png in sorted(pngs.items()):
        # 256 записывается нулём: в поле один байт, и 256 в него не влезает
        byte = 0 if size >= 256 else size
        entries.append(struct.pack(
            "<BBBBHHII", byte, byte, 0, 0, 1, 32, len(png), offset))
        blobs.append(png)
        offset += len(png)
    return header + b"".join(entries) + b"".join(blobs)


def build_preview(pngs: dict[int, bytes]) -> None:
    """Полоса со всеми размерами — чтобы посмотреть глазами, а не гадать."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    pad, sizes = 12, sorted(pngs)
    width = sum(sizes) + pad * (len(sizes) + 1)
    strip = QImage(width, 256 + pad * 2, QImage.Format_ARGB32)
    strip.fill(Qt.white)
    painter = QPainter(strip)
    x = pad
    for size in sizes:
        piece = QImage.fromData(pngs[size], "PNG")
        painter.drawImage(x, pad + 256 - size, piece)
        x += size + pad
    painter.end()
    strip.save(str(PREVIEW), "PNG")


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication(sys.argv)        # QImage без него не рисует
    for source in (SVG, SVG_SMALL):
        if not source.is_file():
            print(f"нет исходника: {source}")
            return 1

    pngs = {size: render(size) for size in SIZES}
    ICO.write_bytes(build_ico(pngs))
    APP_PNG.write_bytes(pngs[256])
    build_preview(pngs)
    print(f"-> {ICO.name}  ({ICO.stat().st_size / 1024:.1f} КБ, "
          f"размеры: {', '.join(str(s) for s in SIZES)})")
    print(f"-> {APP_PNG.relative_to(ROOT)}")
    print(f"-> {PREVIEW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

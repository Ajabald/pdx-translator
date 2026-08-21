"""Building `pdx-translator.ico` out of `tools/appicon.svg`.

    .venv\\Scripts\\python.exe tools\\make_icon.py

It sets up no new dependencies: Qt does the drawing (`QtSvg` is in PySide6
already), and the ICO container is put together here by hand — `QImageWriter`
cannot write a multi-size ICO, it lays in one picture.

The sizes taken are the ones Windows really asks for: 16 — the taskbar and the
title of the window, 32 — the desktop, 48 — "large icons", 256 — "extra large"
and the preview in the explorer. The intermediate 64 and 128 are added so that
the system does not scale 256 down into a "tile".

The data goes into PNG and not BMP: Vista and newer understand that, and the file
comes out three times smaller — 256×256 in BMP would take 256 KB for one size.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "tools" / "appicon.svg"
SVG_SMALL = ROOT / "tools" / "appicon-small.svg"
# Below this size we take the simplified drawing: on such a grid the columns
# merge into a grey dot, and a coarse sign reads better than a detailed one.
SMALL_UPTO = 32
ICO = ROOT / "pdx-translator.ico"
PREVIEW = ROOT / "tools" / "appicon-preview.png"
# A copy inside the package: the `.ico` in the spec sets the icon of the exe
# ITSELF, while the icon of the window and of the taskbar is set by
# `QApplication.setWindowIcon`, and that one needs a file which reaches both the
# build and a run from the sources.
APP_PNG = ROOT / "src" / "pdxloc" / "gui" / "icons" / "app.png"

SIZES = (16, 32, 48, 64, 128, 256)


def render(size: int) -> bytes:
    """A PNG of the needed size out of the SVG — the detailed one or the simplified."""
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
    """The ICO container: the header, the table of records, then the PNGs themselves."""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)      # reserved, type=icon, count
    offset = 6 + 16 * count
    entries, blobs = [], []
    for size, png in sorted(pngs.items()):
        # 256 is written as zero: the field is one byte, and 256 does not fit in it
        byte = 0 if size >= 256 else size
        entries.append(struct.pack(
            "<BBBBHHII", byte, byte, 0, 0, 1, 32, len(png), offset))
        blobs.append(png)
        offset += len(png)
    return header + b"".join(entries) + b"".join(blobs)


def build_preview(pngs: dict[int, bytes]) -> None:
    """A strip with every size — to look with one's own eyes instead of guessing."""
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

    QGuiApplication(sys.argv)        # without it QImage does not draw
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

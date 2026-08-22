# PyInstaller: building the portable version.
#   .venv\Scripts\pyinstaller.exe pdx-translator.spec
#
# Built into a folder (onedir) rather than a single file: a lone exe unpacks
# itself at every start (a slow one) and often trips antivirus heuristics.
# Next to the exe the application creates Bdd and Projects — the mode is portable.

block_cipher = None

# --- the properties of the exe --------------------------------------------
#
# Without a version resource the file has an empty «Details» tab, and that is no
# cosmetic matter: a nameless exe with no publisher and no description is a
# textbook sign for antivirus heuristics, and we have nothing to sign the build
# with.
#
# The version is NOT duplicated here as a string but read out of
# `pdxloc.__init__`: duplicated, it parts ways with the real one at the very
# first release, and there is nobody to notice — nobody reads the properties of a
# file until they are needed. Parsed by a regex rather than imported: the spec
# runs before the package is on the path, and an import would drag PySide6 along
# for the sake of one line.

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo,
)

_init = Path("src/pdxloc/__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _init).group(1)
COPYRIGHT = re.search(r'COPYRIGHT\s*=\s*"([^"]+)"', _init).group(1)

# Windows wants exactly four numbers; «0.1.0» becomes (0, 1, 0, 0).
_numbers = tuple(int(p) for p in VERSION.split(".")) + (0, 0, 0, 0)
FILEVERS = _numbers[:4]

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=FILEVERS, prodvers=FILEVERS,
                      mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1),
    kids=[
        # Code page 04B0 is Unicode. Language 0000 is «neutral» rather than
        # English: the interface switches between three languages, and declaring
        # the file English would be untrue.
        StringFileInfo([StringTable("000004B0", [
            StringStruct("CompanyName", "Ajabald"),
            StringStruct("ProductName", "PDX Translator"),
            StringStruct("FileDescription",
                         "Offline workbench for translating Paradox mod localisation"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("InternalName", "pdx-translator"),
            StringStruct("OriginalFilename", "pdx-translator.exe"),
            StringStruct("LegalCopyright", f"{COPYRIGHT}. GNU GPL v3 or later."),
        ])]),
        VarFileInfo([VarStruct("Translation", [0, 1200])]),
    ],
)

a = Analysis(
    ["src/pdxloc/__main__.py"],
    pathex=["src"],
    binaries=[],
    # The toolbar and menu icons are files inside the package — without them the
    # buttons quietly fall back to the standard Qt style icons. The interface
    # translations are there for the same reason: without the .qm the application
    # quietly stays English.
    datas=[
        ("src/pdxloc/gui/icons", "pdxloc/gui/icons"),
        ("src/pdxloc/gui/translations", "pdxloc/gui/translations"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts",
        "tkinter", "unittest", "pydoc_data",
    ],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pdx-translator",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # a windowed application, no console
    # The icon of the exe itself. It does NOT set the icon of the window and of
    # the taskbar — that one is set by `app.setWindowIcon` from
    # `gui/icons/app.png`. Both files are built by `tools/make_icon.py` out of
    # one source.
    icon="pdx-translator.ico",
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="pdx-translator",
)

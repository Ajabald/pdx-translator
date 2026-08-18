# PyInstaller: сборка портативной версии.
#   .venv\Scripts\pyinstaller.exe pdx-translator.spec
#
# Сборка в папку (onedir), а не в один файл: одиночный exe распаковывается при
# каждом запуске (медленный старт) и часто ловит ложные срабатывания антивирусов.
# Рядом с exe приложение создаёт папки Bdd и Projects — режим переносимый.

block_cipher = None

# --- свойства exe ---------------------------------------------------------
#
# Без ресурса версии у файла пустая вкладка «Подробно», и это не косметика:
# безымянный exe без издателя и описания — типовой признак для эвристик
# антивирусов, а подписывать сборку нам нечем.
#
# Версия НЕ дублируется здесь строкой, а читается из `pdxloc.__init__`:
# продублированная, она разъезжается с настоящей на первом же выпуске, и
# заметить это некому — свойства файла никто не читает, пока не понадобятся.
# Разбор регуляркой, а не импортом: спека выполняется до того, как пакет
# оказывается на пути, и импорт тянул бы за собой PySide6 ради одной строки.

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo,
)

_init = Path("src/pdxloc/__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _init).group(1)
COPYRIGHT = re.search(r'COPYRIGHT\s*=\s*"([^"]+)"', _init).group(1)

# Windows хочет ровно четыре числа; «0.1.0» превращается в (0, 1, 0, 0).
_numbers = tuple(int(p) for p in VERSION.split(".")) + (0, 0, 0, 0)
FILEVERS = _numbers[:4]

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=FILEVERS, prodvers=FILEVERS,
                      mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1),
    kids=[
        # Кодовая страница 04B0 — Unicode. Язык 0000 «нейтральный», а не
        # английский: интерфейс переключается между тремя языками, и объявлять
        # файл англоязычным было бы неправдой.
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
    # Иконки панели и меню лежат файлами внутри пакета — без них кнопки
    # молча уедут на стандартные иконки стиля Qt. Переводы интерфейса — там же
    # и по той же причине: без .qm приложение молча остаётся английским.
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
    console=False,          # оконное приложение, без консоли
    # Иконка самого exe. Иконку окна и панели задач она НЕ задаёт — ту ставит
    # `app.setWindowIcon` из `gui/icons/app.png`. Оба файла собирает
    # `tools/make_icon.py` из одного исходника.
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

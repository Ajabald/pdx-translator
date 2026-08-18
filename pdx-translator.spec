# PyInstaller: сборка портативной версии.
#   .venv\Scripts\pyinstaller.exe pdx-translator.spec
#
# Сборка в папку (onedir), а не в один файл: одиночный exe распаковывается при
# каждом запуске (медленный старт) и часто ловит ложные срабатывания антивирусов.
# Рядом с exe приложение создаёт папки Bdd и Projects — режим переносимый.

block_cipher = None

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
    icon=None,              # TODO: добавить иконку перед публикацией
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

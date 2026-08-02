"""Точка входа: GUI по умолчанию, headless-режим --scan-cli для отладки/скриптов."""
from __future__ import annotations

import argparse
import sys


def _scan_cli(args: argparse.Namespace) -> int:
    """Скан без Qt: открыть (или создать) файл проекта и просканировать."""
    from pathlib import Path

    from ck3loc import project
    from ck3loc.core.scanner import scan_project
    from ck3loc.core.stats import format_status_bar, project_stats

    path = Path(args.project)
    if args.create:
        name, src_root, tgt_root = args.create
        conn = project.create_project(
            path, name=name, src_root=src_root, tgt_root=tgt_root,
            src_lang=args.src_lang, tgt_lang=args.tgt_lang)
        print(f"Создан проект: {path}")
    else:
        if not path.is_file():
            print(f"Файл проекта не найден: {path}")
            return 1
        conn = project.open_project(path)

    def progress(done: int, total: int, name: str) -> None:
        print(f"  [{done}/{total}] {name}")

    stats = scan_project(conn, 1, progress)
    print()
    print(stats.summary_ru())
    for w in stats.parse_warnings:
        print("  ПРЕДУПРЕЖДЕНИЕ:", w)
    for d in stats.duplicate_keys:
        print("  ДУБЛИКАТ:", d)
    print("\n" + format_status_bar(project_stats(conn, 1)))
    conn.close()
    return 0


def _install_qt_translations(app) -> None:
    """Русские подписи стандартных кнопок Qt («Close» → «Закрыть» и прочие).

    Без этого встроенные кнопки диалогов и контекстные меню полей ввода
    остаются английскими посреди русского интерфейса.
    """
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    app._translators = []          # держим ссылки: иначе сборщик мусора их съест
    for name in ("qtbase", "qt"):
        translator = QTranslator(app)
        if translator.load(QLocale("ru"), name, "_", path):
            app.installTranslator(translator)
            app._translators.append(translator)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ck3-translator")
    parser.add_argument("--project", help="Путь к файлу проекта (*.ck3proj)")
    parser.add_argument("--scan", action="store_true", help="Просканировать проект и выйти")
    parser.add_argument("--create", nargs=3, metavar=("NAME", "SRC_ROOT", "TGT_ROOT"),
                        help="Создать проект по пути --project")
    parser.add_argument("--src-lang", default="english", help="Язык оригинала")
    parser.add_argument("--tgt-lang", default="russian", help="Язык перевода")
    args = parser.parse_args()

    if args.project and (args.scan or args.create):
        return _scan_cli(args)

    # GUI
    from PySide6.QtWidgets import QApplication

    from ck3loc.gui import theme
    from ck3loc.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")      # своя палитра ложится только на Fusion
    app.setApplicationName("CK3 Translator")
    _install_qt_translations(app)
    theme.apply_saved(app)
    window = MainWindow()
    window.show()
    return app.exec()

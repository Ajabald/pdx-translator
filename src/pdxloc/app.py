"""Точка входа: GUI по умолчанию, headless-режим --scan-cli для отладки/скриптов."""
from __future__ import annotations

import argparse
import sys


def _scan_cli(args: argparse.Namespace) -> int:
    """Скан без Qt: открыть (или создать) файл проекта и просканировать."""
    from pathlib import Path

    from pdxloc import project
    from pdxloc.core.scanner import scan_project
    from pdxloc.core.stats import format_status_bar, project_stats

    path = Path(args.project)
    if args.create:
        name, src_root, tgt_root = args.create
        conn = project.create_project(
            path, name=name, src_root=src_root, tgt_root=tgt_root,
            src_lang=args.src_lang, tgt_lang=args.tgt_lang)
        print(f"Project created: {path}")
    else:
        if not path.is_file():
            print(f"Project file not found: {path}")
            return 1
        conn = project.open_project(path)

    def progress(done: int, total: int, name: str) -> None:
        print(f"  [{done}/{total}] {name}")

    stats = scan_project(conn, 1, progress)
    print()
    print(stats.summary())
    for w in stats.parse_warnings:
        print("  WARNING:", w)
    for d in stats.duplicate_keys:
        print("  DUPLICATE:", d)
    for k in stats.empty_source_keys:
        print("  EMPTY:", k)
    print("\n" + format_status_bar(project_stats(conn, 1)))
    conn.close()
    return 0


def main() -> int:
    # Подсказки командной строки не переводятся: режим отладочный, переводчик
    # к моменту разбора аргументов ещё не установлен, а Qt может не быть вовсе.
    parser = argparse.ArgumentParser(prog="pdx-translator")
    parser.add_argument("--project", help="Path to the project file (*.pdxproj)")
    parser.add_argument("--scan", action="store_true",
                        help="Scan the project and exit")
    parser.add_argument("--create", nargs=3, metavar=("NAME", "SRC_ROOT", "TGT_ROOT"),
                        help="Create a project at the --project path")
    parser.add_argument("--src-lang", default="english", help="Original language")
    parser.add_argument("--tgt-lang", default="russian", help="Translation language")
    args = parser.parse_args()

    if args.project and (args.scan or args.create):
        return _scan_cli(args)

    # GUI
    from PySide6.QtWidgets import QApplication

    from pdxloc.gui import language, theme
    from pdxloc.gui.main_window import MainWindow

    from pdxloc import settings

    app = QApplication(sys.argv)
    app.setStyle("Fusion")      # своя палитра ложится только на Fusion
    app.setApplicationName("PDX Translator")
    # Настройки прежнего имени — до всего остального: язык и тема читаются уже
    # из своего куста, и перенимать их после было бы поздно
    settings.adopt_previous_settings()
    # язык до создания окна: иначе меню соберётся на языке оригинала и его
    # придётся перерисовывать ещё до первого показа
    language.apply_saved(app)
    theme.apply_saved(app)
    window = MainWindow()
    window.show()
    return app.exec()

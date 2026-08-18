"""Обращения к проводнику Windows — все в одном месте.

Здесь ровно одна нетривиальная вещь, ради которой модуль и заведён:
`explorer /select,` нельзя вызывать списком аргументов. Python склеивает
список через `subprocess.list2cmdline`, тот вставляет пробел после запятой, и
получается `explorer /select, "D:\\путь"` — такую строку проводник не
разбирает и молча открывает папку по умолчанию вместо нужного файла. Именно
поэтому «Открыть оригинал в проводнике» показывало «Документы».
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def reveal(path: Path) -> None:
    """Показать файл в проводнике, выделив его.

    Если файла нет — открываем хотя бы его папку: молчать в ответ на нажатие
    кнопки хуже, чем показать не совсем то.
    """
    target = Path(path)
    if target.exists():
        native = os.path.normpath(str(target))
        subprocess.Popen(f'explorer /select,"{native}"')     # строкой, не списком
    else:
        open_dir(target.parent)


def open_dir(path: Path) -> None:
    """Открыть папку в проводнике, создав её при необходимости."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", os.path.normpath(str(target))])

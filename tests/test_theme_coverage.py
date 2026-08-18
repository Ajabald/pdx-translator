"""Все цвета интерфейса живут в theme.py и нигде больше.

Литерал цвета в модуле виджета — это цвет, который не поменяется вместе с
темой. Так на тёмной теме уже становились нечитаемыми подписи-подсказки,
дерево файлов и записи подключённых баз памяти. Проверка грепом дешевле, чем
осмотр глазами каждого нового окна.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1] / "src" / "pdxloc" / "gui"

# и #rgb, и #rrggbb, и #aarrggbb
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# В таблице стилей цвет бывает и словом («red»), а не только шестнадцатеричным
# литералом. Ловим значение, записанное прямо в строку: если оно начинается с
# «{», это подстановка из темы — такие пропускаем. Смотрим только внутри
# строковых литералов, иначе под правило попадает аннотация `color: str`.
STRING = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
CSS_COLOR = re.compile(r"\b(?:color|background)\s*:\s*(?!\{)[^;{}]*[a-zA-Z#]")

# theme.py — единственное законное место; icons.py красит через theme.color()
ALLOWED = {"theme.py"}


def gui_modules() -> list[Path]:
    return sorted(p for p in GUI.glob("*.py") if p.name not in ALLOWED)


@pytest.mark.parametrize("path", gui_modules(), ids=lambda p: p.name)
def test_no_hardcoded_colour_literals(path: Path) -> None:
    hits = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if HEX.search(line)
    ]
    assert not hits, (
        "Цвет должен приходить из theme.color()/theme.qcolor(), иначе он не "
        "поменяется вместе с темой:\n" + "\n".join(hits))


@pytest.mark.parametrize("path", gui_modules(), ids=lambda p: p.name)
def test_stylesheets_take_colour_from_theme(path: Path) -> None:
    """setStyleSheet допустим, но цвет в нём — только подстановкой из темы."""
    hits = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(CSS_COLOR.search(s.group(0)) for s in STRING.finditer(line))
    ]
    assert not hits, (
        "В таблице стилей цвет задан мимо темы:\n" + "\n".join(hits))

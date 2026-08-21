"""Every colour of the interface lives in theme.py and nowhere else.

A colour literal in the module of a widget is a colour that will not change
together with the theme. That is how the hint labels, the file tree and the
records of attached memory databases have already become unreadable on the dark
theme. A check by grep is cheaper than looking over every new window by eye.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1] / "src" / "pdxloc" / "gui"

# both #rgb, and #rrggbb, and #aarrggbb
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# In a stylesheet a colour happens to be a word («red») too, not only a hexadecimal
# literal. We catch a value written right into a string: if it starts with «{», it
# is a substitution from the theme — such we skip. We look only inside string
# literals, otherwise the annotation `color: str` falls under the rule.
STRING = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
CSS_COLOR = re.compile(r"\b(?:color|background)\s*:\s*(?!\{)[^;{}]*[a-zA-Z#]")

# theme.py is the only lawful place; icons.py paints through theme.color()
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
    """setStyleSheet is allowed, but a colour in it comes only as a substitution from the theme."""
    hits = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(CSS_COLOR.search(s.group(0)) for s in STRING.finditer(line))
    ]
    assert not hits, (
        "В таблице стилей цвет задан мимо темы:\n" + "\n".join(hits))

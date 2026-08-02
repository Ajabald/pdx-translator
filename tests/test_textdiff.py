"""Тесты сравнения редакций оригинала."""
from __future__ import annotations

import pytest

from ck3loc.core.textdiff import (
    COSMETIC, MEANINGFUL, changed_ranges, classify_change, summarize_change, word_diff,
)


@pytest.mark.parametrize("old,new", [
    ("Winter is coming", "Winter is coming."),                 # добавлена точка
    ("Winter is coming", "Winter  is   coming"),               # лишние пробелы
    ("Winter is Coming", "winter is coming"),                  # регистр
    ("Hello, world!", "Hello world"),                          # пунктуация
    ("A quote — dash", "A quote - dash"),                      # тире
])
def test_cosmetic(old, new):
    assert classify_change(old, new) == COSMETIC


@pytest.mark.parametrize("old,new", [
    ("Winter is coming", "Summer is coming"),                  # слово
    ("Gain 10 gold", "Gain 20 gold"),                          # число
    ("Winter is coming", "Winter is coming soon"),             # добавлено слово
    ("Plain text", "#bold Plain text#!"),                      # появилась разметка
    ("Gain $VALUE$", "Gain $AMOUNT$"),                         # другая переменная
    ("Cost £gold£", "Cost £prestige£"),                        # другая иконка
])
def test_meaningful(old, new):
    assert classify_change(old, new) == MEANINGFUL


def test_markup_change_is_meaningful_even_with_same_words():
    """Разметку придётся перенести в перевод — это не косметика."""
    assert classify_change("The #weak north#!", "The #bold north#!") == MEANINGFUL


def test_changed_ranges_point_at_new_text():
    old = "Winter is coming"
    new = "Winter is coming soon"
    ranges = changed_ranges(old, new)
    assert ranges
    assert "".join(new[s:e] for s, e in ranges) == "soon"


def test_changed_ranges_middle_replacement():
    old = "The old lord of Winterfell"
    new = "The young lord of Winterfell"
    ranges = changed_ranges(old, new)
    assert [new[s:e] for s, e in ranges] == ["young"]


def test_changed_ranges_no_change():
    assert changed_ranges("Same text", "Same text") == []


def test_changed_ranges_within_bounds():
    old, new = "a b c", "a x y z c"
    for start, end in changed_ranges(old, new):
        assert 0 <= start < end <= len(new)


def test_word_diff_reconstructs_texts():
    """Дифф пословный, поэтому сверяем слова: пробелы между ними не значимы."""
    old, new = "Winter is coming", "Winter is coming soon"
    parts = word_diff(old, new)
    assert "".join(t for op, t in parts if op in ("equal", "insert")).split() == new.split()
    assert "".join(t for op, t in parts if op in ("equal", "delete")).split() == old.split()
    assert ("insert", "soon") in [(op, t.strip()) for op, t in parts]


def test_summarize_change():
    assert "косметическая" in summarize_change("Text", "Text.")
    text = summarize_change("Winter is coming", "Summer is coming")
    assert "изменён текст" in text and "Summer" in text

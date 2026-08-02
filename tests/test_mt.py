"""Тесты каркаса машинного перевода: защита разметки CK3."""
from __future__ import annotations

import pytest

from ck3loc.core import mt

REAL_STRINGS = [
    "Gain [GetTrait('brave').GetName] and $VALUE$ £gold£",
    "#bold Important#! text with\\nline break",
    "[GetPlayer.GetDynasty.GetNameNoTooltip]",
    "Cost: $VALUE|=+0$ £prestige£, see [men_at_arms|E]",
    "#high;italic Fancy#! and #weak quiet#!",
    "Plain text without any markup",
    "",
]


@pytest.mark.parametrize("text", REAL_STRINGS)
def test_shield_unshield_roundtrip(text):
    shielded, mapping = mt.shield_tags(text)
    assert mt.unshield(shielded, mapping) == text


def test_markup_is_hidden_from_translator():
    text = "Gain [GetTrait('brave').GetName] and $VALUE$"
    shielded, mapping = mt.shield_tags(text)
    assert "[" not in shielded and "$" not in shielded
    assert len(mapping) == 2
    assert "⟦0⟧" in shielded and "⟦1⟧" in shielded


def test_words_remain_translatable():
    shielded, _ = mt.shield_tags("Gain #bold gold#! now")
    assert "Gain" in shielded and "gold" in shielded and "now" in shielded


def test_unshield_tolerates_spacing():
    text = "Value: $VALUE$"
    shielded, mapping = mt.shield_tags(text)
    damaged = shielded.replace("⟦0⟧", "⟦ 0 ⟧")     # переводчик добавил пробелы
    assert mt.unshield(damaged, mapping) == text


def test_missing_tokens_detected():
    text = "Gain $VALUE$ £gold£"
    shielded, mapping = mt.shield_tags(text)
    assert mt.missing_tokens(shielded, mapping) == []
    assert len(mt.missing_tokens("перевод без меток", mapping)) == 2


def test_nested_formatting_not_double_wrapped():
    text = "#bold [GetName]#!"
    shielded, mapping = mt.shield_tags(text)
    assert mt.unshield(shielded, mapping) == text
    assert len(mapping) == 3      # #bold, [GetName], #!


def test_translate_texts_with_stub_provider():
    provider = mt.get_provider("none")
    assert provider.name == "none"
    results = mt.translate_texts(provider, REAL_STRINGS[:3], "english", "russian")
    assert [text for text, _ in results] == REAL_STRINGS[:3]
    assert all(not missing for _, missing in results)


def test_translate_reports_broken_markup():
    class BrokenProvider:
        name = "broken"

        def translate_batch(self, texts, src_lang, tgt_lang):
            return ["перевод без меток" for _ in texts]

    results = mt.translate_texts(
        BrokenProvider(), ["Gain $VALUE$ £gold£"], "english", "russian")
    text, missing = results[0]
    assert len(missing) == 2       # обе метки потеряны — строку надо проверить


def test_provider_must_return_same_count():
    class BadProvider:
        name = "bad"

        def translate_batch(self, texts, src_lang, tgt_lang):
            return []

    with pytest.raises(RuntimeError):
        mt.translate_texts(BadProvider(), ["a", "b"], "english", "russian")

"""The Paradox markup registry: the composition, the order, and that the move shifted nothing.

`core/markup.py` was set up so that the description of the tokens would be in one
place instead of crawling over five modules (highlighting, machine translation,
the classification of edits, the search for similar rows, the auto-ignore). Here
we check that each of the five gets exactly what it got before — and that the
colours and the order have not come apart.
"""
from __future__ import annotations

import re

import pytest

from pdxloc.core import markup, mt, qa, textdiff, unit_ops
from pdxloc.gui import theme

SAMPLE = ('Cost: $VALUE|=+0$ @gold! £prestige£, see [men_at_arms|E] '
          'and #bold this#!\\nnext line')


# --- the composition and the order --------------------------------------


def test_every_colour_exists_in_both_palettes() -> None:
    """Otherwise the dark theme falls over on the first field with markup."""
    for token in markup.TOKENS:
        if token.color is None:
            continue
        for palette in (theme._LIGHT, theme._DARK):
            assert token.color in palette, f"{token.id}: нет цвета {token.color}"


def test_closing_tag_is_shielded_before_opening_ones() -> None:
    """Otherwise «#!» travels to the translator bare and comes back broken."""
    order = [t.id for t in markup.shield_tokens()]
    assert order.index("fmt_close") < order.index("fmt_open")


def test_parameterised_tag_is_shielded_before_the_plain_one() -> None:
    """Otherwise the tail after the colon travels to the translator as text.

    `#TOOLTIP:hint_key` is the key of a tooltip and not prose: translate it, and
    the tooltip in the game stops being found. 331 such rows in vanilla and in a
    live mod.
    """
    order = [t.id for t in markup.shield_tokens()]
    assert order.index("fmt_param") < order.index("fmt_open")


def test_parameterised_tag_is_shielded_whole() -> None:
    text = "#TOOLTIP:hint_key Text"
    shielded, mapping = mt.shield_tags(text)
    assert "#TOOLTIP:hint_key" in mapping.values()
    assert "hint_key" not in shielded
    assert mt.unshield(shielded, mapping) == text


def test_tooltip_argument_leaves_the_script_call_to_the_bracket() -> None:
    text = "#TOOLTIP:CHARACTER,[CHARACTER.GetID] Name"
    shielded, mapping = mt.shield_tags(text)
    assert "#TOOLTIP:CHARACTER," in mapping.values()
    assert "[CHARACTER.GetID]" in mapping.values()
    assert mt.unshield(shielded, mapping) == text


def test_colour_with_a_script_call_is_deliberately_uncovered() -> None:
    """`#color:{[ToTextFormatColor(…)]}` — four rows over all the corpora.

    A regex that swallowed them whole would take the range away from `bracket`,
    and `shield_tags` (which goes by ranges) would diverge from `strip_markup`
    (which goes by sequential replacement). Written down as a test so that it
    does not look like an oversight.
    """
    assert not markup.pattern("fmt_param").search("#color:{[ToTextFormatColor(x)]}")


def test_at_icon_is_shielded_after_brackets() -> None:
    """Otherwise an icon inside a scripted call steals the range of the whole bracket.

    `shield_tags` takes non-overlapping ranges in the order of the tokens and
    throws away every later one that overlapped with something. Let the `@gold!`
    icon inside `[Select_CString(x,'@gold!','')]` take its own — and the bracket
    would be thrown away whole, and the entire call would travel to the
    translator raw. There are 12 such rows in vanilla and 18 in a live mod.
    """
    order = [t.id for t in markup.shield_tokens()]
    assert order.index("bracket") < order.index("icon_at")
    assert order.index("dollar") < order.index("icon_at")


def test_icon_inside_a_script_call_does_not_steal_the_bracket() -> None:
    """The same order, but checked by behaviour instead of by indices."""
    text = "Pay [Select_CString(x,'@gold!','')] now"
    shielded, mapping = mt.shield_tags(text)
    assert "[Select_CString(x,'@gold!','')]" in mapping.values()
    assert "Select_CString" not in shielded
    assert mt.unshield(shielded, mapping) == text


def test_tokens_of_other_games_are_marked_as_such() -> None:
    """`£…£` and `§Y…§!` are the markup of HOI4/EU4/Stellaris, `@name!` is ours.

    Not one of the foreign tokens turned up in the 289,940 rows of the CK3
    databases, so looking for them always is free; the `game` field stays the
    passport of a token.
    """
    foreign = {"icon_pound", "icon_var", "color_open", "color_close",
               "color_script", "grammar_tags", "grammar_variant"}
    assert {t.id for t in markup.TOKENS if t.game == markup.OTHER} == foreign
    assert markup.BY_ID["icon_at"].game == markup.CK3


def test_colour_close_is_shielded_before_the_opening_one() -> None:
    """The same rule as for `#!`: the closing one is looked for first."""
    order = [t.id for t in markup.shield_tokens()]
    assert order.index("color_close") < order.index("color_open")


def test_hoi4_colour_never_reaches_the_translator() -> None:
    """`§YKing§!` used to travel to the translator raw — the colour came back moved."""
    text = "The §YKing§! has re-established control over §Y[SWE.GetFlag]§! politics."
    shielded, mapping = mt.shield_tags(text)
    assert "§" not in shielded
    assert mt.unshield(shielded, mapping) == text


def test_pound_icon_takes_its_size_flag() -> None:
    """`|8` is the size of an icon and not text: 21 rows of vanilla HOI4."""
    assert markup.strip_markup("£operative_mission_icons_small|8£ Propaganda") == "Propaganda"
    assert markup.strip_markup("£command_power Cost") == "Cost"      # without a pair


def test_colour_and_icon_named_by_a_call_are_taken_whole() -> None:
    """`§[GetColour]` and `£$ICON$£`: a bare symbol would eat a letter of the neighbouring word.

    Both hold another token inside, and the order decides who takes the piece
    first. The colour out of a call is looked for BEFORE the bracket (otherwise a
    `§` is left of it, and that carries off the first letter of the next word:
    `§[GetColour]red` gave `ed`), while a plain `§Y` — AFTER, otherwise a colour
    inside `[Select_CString(…)]` would steal the range of the whole call.
    """
    assert markup.strip_markup("Now §[GetColour]red§!") == "Now red"
    assert markup.strip_markup("£$ICON$£ bonus") == "bonus"
    # a colour inside a scripted call stays part of the call
    call = "[Select_CString(x,'§Ytext§!','')]"
    shielded, mapping = mt.shield_tags(call)
    assert call in mapping.values()
    assert mt.unshield(shielded, mapping) == call


def test_a_pair_of_icons_does_not_merge_with_the_next_variable() -> None:
    """`£command_power£$COST|H0$` — an icon with a pair, then a variable.

    Parse the second £ as the start of an "icon out of a variable", and the pair
    would fall in two: `icon_pound` is looked for before `icon_var` for exactly
    that reason.
    """
    text = "£command_power£$COST|H0$"
    shielded, mapping = mt.shield_tags(text)
    assert "£command_power£" in mapping.values()
    assert "$COST|H0$" in mapping.values()
    assert mt.unshield(shielded, mapping) == text


def test_ids_are_unique() -> None:
    assert len(markup.BY_ID) == len(markup.TOKENS)


def test_every_token_has_an_order() -> None:
    orders = [t.order for t in markup.TOKENS]
    assert len(set(orders)) == len(orders), "одинаковый order делает порядок случайным"


# --- the behaviour is preserved -----------------------------------------


FROZEN_STRIP = (
    ("Cost: $VALUE$ gold", "Cost:  gold"),
    ("[GetName] rules", "rules"),
    ("#bold Text#!", "Text"),
    ("line\\nbreak", "line break"),
    ("£gold£ only", "only"),
    ("@gold! paid", "paid"),
    ("@warning_icon! [GetName]", ""),
    ("#indent_newline:2 Text", "Text"),
    ("#TOOLTIP:CHARACTER,[CHARACTER.GetID] Name", "Name"),
    ("#color:{0.8,0.7,0.5};bold Red#!", "Red"),
    ("", ""),
)


@pytest.mark.parametrize("text,expected", FROZEN_STRIP)
def test_strip_markup_unchanged(text: str, expected: str) -> None:
    assert markup.strip_markup(text) == expected
    assert qa.strip_markup(text) == expected      # the old name still works


def test_qa_aliases_point_at_the_registry() -> None:
    """The tests and the old code go by the RE_* names — those are obliged to stay the same."""
    assert qa.RE_BRACKET is markup.pattern("bracket")
    assert qa.RE_DOLLAR is markup.pattern("dollar")
    assert qa.RE_ICON is markup.pattern("icon_pound")
    assert qa.RE_ICON_AT is markup.pattern("icon_at")
    assert qa.RE_FMT_OPEN is markup.pattern("fmt_open")
    assert qa.RE_FMT_CLOSE is markup.pattern("fmt_close")
    assert qa.RE_NEWLINE is markup.pattern("newline")


def test_shield_round_trip_keeps_every_token() -> None:
    shielded, mapping = mt.shield_tags(SAMPLE)
    assert mt.unshield(shielded, mapping) == SAMPLE
    # not one piece of markup must be left in the text that goes off to be translated
    for token in markup.shield_tokens():
        assert not token.pattern.search(shielded), token.id


def test_markup_only_still_recognised() -> None:
    """It feeds the auto-ignore at a scan — a shift here changes statuses silently."""
    assert unit_ops.is_markup_only("[GetPlayer.GetDynasty.GetName]")
    assert unit_ops.is_markup_only("$VALUE$")
    assert unit_ops.is_markup_only("[A] [B]\\n$C$")
    assert unit_ops.is_markup_only("@gold! [GetName]")
    assert not unit_ops.is_markup_only("@gold! Attack")
    assert not unit_ops.is_markup_only("House [GetName]")
    assert not unit_ops.is_markup_only("Hello")
    assert not unit_ops.is_markup_only("")


def test_change_classification_still_sees_markup() -> None:
    """It affects the «Stale» status — an edit of markup is obliged to stay a meaningful one."""
    assert textdiff.classify_change(
        "Hello [GetA]", "Hello [GetB]") == textdiff.MEANINGFUL
    assert textdiff.classify_change(
        "Hello world", "Hello, world!") == textdiff.COSMETIC


def test_highlight_rules_cover_the_visible_tokens() -> None:
    rules = markup.highlight_rules()
    assert all(isinstance(p, re.Pattern) for p, _, _ in rules)
    coloured = {t.id for t in markup.TOKENS if t.color}
    assert coloured == {"bracket", "dollar", "icon_pound", "icon_var", "icon_at",
                        "fmt_open", "fmt_param", "fmt_close", "escape",
                        "color_open", "color_close", "color_script",
                        "grammar_tags", "grammar_variant"}
    # the formatting is set in bold, the references are not
    by_pattern = {p: bold for p, _, bold in rules}
    assert by_pattern[markup.pattern("fmt_open")] is True
    assert by_pattern[markup.pattern("fmt_param")] is True
    assert by_pattern[markup.pattern("bracket")] is False


def test_stellaris_grammar_is_shielded_and_stripped() -> None:
    """`&!fem` and `|||gen:` are Stellaris grammar, not text.

    The game picks a variant of a name by the tags, and that must not travel to
    the translator: the Russian tree holds 6,327 rows with variants and 2,278
    with tags.
    """
    text = "энергия&!fem|||gen:энергии"
    shielded, mapping = mt.shield_tags(text)
    assert "&!" not in shielded and "|||" not in shielded
    assert mt.unshield(shielded, mapping) == text
    # the variants are parted by a space, otherwise the words stick into one
    assert markup.strip_markup(text) == "энергия энергии"


def test_a_variant_inside_a_script_call_stays_part_of_the_call() -> None:
    """`[leader.GetAXX::вернулся|||fem:вернулась]` — one call, not three pieces."""
    call = "[leader.GetAXX::вернулся|||fem:вернулась]"
    shielded, mapping = mt.shield_tags(call)
    assert call in mapping.values()
    assert mt.unshield(shielded, mapping) == call


def test_tag_forwarding_control_is_a_tag_too() -> None:
    """`&!0` stops the forwarding of tags to a subname — markup as well, not text."""
    assert markup.strip_markup("Coalition of $1$&!0") == "Coalition of"

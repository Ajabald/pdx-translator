"""Tests of the QA checks: a positive and a negative for every code."""
from __future__ import annotations

from pdxloc.core.qa import check_unit, strip_markup


def test_ok_translation_no_issues():
    en = 'Gain #bold [GetTrait(\'brave\').GetName]#! and $VALUE$ £gold£'
    ru = 'Получить #bold [GetTrait(\'brave\').GetName]#! и $VALUE$ £gold£'
    assert check_unit(en, ru) == []


def test_dollar_mismatch():
    assert "dollar_mismatch" in check_unit("Cost: $VALUE$", "Цена: непонятно")
    assert "dollar_mismatch" not in check_unit("Cost: $VALUE$", "Цена: $VALUE$")


def test_dollar_with_format_pipe():
    assert check_unit("Bonus $VAL|=+0$", "Бонус $VAL|=+0$") == []


def test_dollar_only_if_all_lost_separates_a_hole_from_a_reshuffle():
    """A measurement on a live translation parted two cases under one code.

    789 hits out of 1413 are "not a single variable is left in the translation",
    that is, a hole in the text right in the game; the other 624 are "the set
    differs", and that is more often a deliberate reshuffle. A preset does not
    cure such a thing: the rule needs a parameter of its own, and it is off by
    default — a replacement happens to be an error too.
    """
    from pdxloc.core import qa_rules

    strict = qa_rules.default_ruleset().restricted_to({"dollar_mismatch"})
    lenient = strict.with_rule(
        strict.get("dollar_mismatch").with_params(only_if_all_lost=True))

    assert strict.check("$A$ and $B$", "текст") == ["dollar_mismatch"]
    assert lenient.check("$A$ and $B$", "текст") == ["dollar_mismatch"]

    assert strict.check("$A$ and $B$", "$A$ текст") == ["dollar_mismatch"]
    assert lenient.check("$A$ and $B$", "$A$ текст") == []
    # and where there were no variables at all, the leniency invents no remarks
    assert lenient.check("plain", "просто текст") == []


def test_icon_mismatch():
    assert "icon_mismatch" in check_unit("Pay £gold£", "Заплатить золотом")


def test_unclosed_tag_in_original_is_not_an_error():
    """The main fix of v4: in CK3 a tag at the end of a row need not be closed.

    The former rule demanded a balance of #tags and #! in the translation and
    gave 826 false hits out of 827 on a live project.
    """
    en = "Some text.\\n#weak Words fade; writs remain."
    ru = "Некий текст.\\n#weak Слова тускнеют, записи остаются."
    assert check_unit(en, ru) == []


def test_fmt_broken_when_original_is_closed():
    """But if the tag is closed in the original and not in the translation — that is an error."""
    assert "fmt_broken" in check_unit("#weak text#!", "#weak текст")


def test_fmt_mismatch_different_tags():
    codes = check_unit("#weak text#!", "#bold текст#!")
    assert "fmt_mismatch" in codes
    assert "fmt_broken" not in codes


def test_semicolon_tag():
    assert check_unit("#high;italic text#!", "#high;italic текст#!") == []


def test_brackets_mismatch_is_warning_code():
    codes = check_unit("[GetTrait('brave').GetName] is brave", "Просто храбрый")
    assert "brackets_mismatch" in codes


def test_newline_mismatch():
    assert "newline_mismatch" in check_unit("a\\nb", "аб")
    assert "newline_mismatch" not in check_unit("a\\nb", "а\\nб")


def test_paragraph_break_is_not_a_double_space():
    """A regression: a paragraph break was declared a typo.

    A line break in the Paradox format is written with two characters — a
    backslash and an «n». The rule replaced every such break with a space and
    then looked for two spaces in a row, so any paragraph break `\\n\\n` looked
    like a double space. On a live project 84 translations out of 4851 were
    marked that way — all of them falsely.
    """
    assert "double_space" not in check_unit("Dawn.\\n\\nThen night.", "Рассвет.\\n\\nПотом ночь.")
    # a space next to a break is not a double space either
    assert "double_space" not in check_unit("a\\nb", "а \\n б")


def test_double_space_still_caught():
    assert "double_space" in check_unit("Two words", "Два  слова")
    assert "double_space" in check_unit("a\\nb", "аа  бб\\nвв")
    # edge spaces are a remark of their own, not a double space
    codes = check_unit("Text", "  текст")
    assert "edge_space" in codes and "double_space" not in codes


def test_empty_translated():
    assert check_unit("Text", "   ") == ["empty_translated"]


def test_same_as_en():
    assert "same_as_en" in check_unit("Same text here", "Same text here")


def test_len_ratio_disabled_by_default():
    """The length heuristic is noisy (208 hits on live data) — it is off by default."""
    en = "This is a fairly long English sentence for the ratio check."
    assert "len_ratio" not in check_unit(en, "Да.")
    assert "len_ratio" in check_unit(en, "Да.", enabled={"len_ratio"})


def test_len_ratio_skips_short():
    assert "len_ratio" not in check_unit(
        "Short", "Оч. длинный перевод короткого слова", enabled={"len_ratio"})


def test_edge_and_double_spaces():
    assert "edge_space" in check_unit("Text here", " Текст ")
    assert "double_space" in check_unit("Text here", "Текст  здесь")
    assert check_unit("Text here", "Текст здесь") == []


def test_unbalanced_quotes():
    assert "unbalanced_quotes" in check_unit("He said hi", 'Он сказал "привет')
    assert "unbalanced_quotes" in check_unit("Text (here)", "Текст (здесь")
    assert "unbalanced_quotes" not in check_unit("Text (here)", "Текст (здесь)")


def test_enabled_filter_limits_checks():
    codes = check_unit("Cost: $VALUE$", "Цена  без переменной", enabled={"double_space"})
    assert codes == ["double_space"]


def test_strip_markup():
    s = strip_markup('#bold Hello#! [GetName] $V$ £gold£\\nWorld')
    assert "Hello" in s and "World" in s
    assert "[" not in s and "$" not in s and "£" not in s and "#" not in s


# --- HOI4: the colour, the declensions, the preset -----------------------


def test_color_mismatch():
    assert "color_mismatch" in check_unit("§YWarning§!", "Внимание")
    assert "color_mismatch" in check_unit("§YWarning§!", "§RВнимание§!")   # the colour is swapped
    assert check_unit("§YWarning§!", "§YВнимание§!") == []


def test_colour_from_a_script_call_is_a_colour_too():
    assert check_unit("§[GetColour]Text§!", "§[GetColour]Текст§!") == []
    assert "color_mismatch" in check_unit("§[GetColour]Text§!", "Текст")


def test_icon_named_by_a_variable_is_checked():
    assert check_unit("£$ICON$£ bonus", "£$ICON$£ бонус") == []
    assert "icon_mismatch" in check_unit("£$ICON$£ bonus", "бонус")


def test_russian_hoi4_inflection_is_a_technique_not_a_loss():
    """`[JAP.GetAdjective]` → `[JAP.GetAdjRuLower]ие` is a device of the game itself.

    The built-in set counts that as a lost reference (5,028 rows of the vanilla
    Russian HOI4), the `hoi4_ru` preset does not. Exactly one token is forgiven
    per replacement: a real loss is obliged to stay visible.
    """
    from pdxloc.core import qa_rules

    en = "Cancel the [JAP.GetAdjective] rights in [655.GetName]"
    ru = "Отменить [JAP.GetAdjRuLower]ие права в регионе [655.GetName]"
    assert "brackets_mismatch" in check_unit(en, ru)

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert hoi4.check(en, ru) == []
    # a lost second reference is not forgiven
    assert "brackets_mismatch" in hoi4.check(
        en, "Отменить [JAP.GetAdjRuLower]ие права")


def test_a_typo_in_a_function_name_is_not_forgiven():
    """`GetADjectiveCap` and `GetAdejctive` are live typos of the vanilla translation.

    The list of declining functions is gathered from those that are never met in
    the English tree; a typo is not met there either, and forgiving it would be
    convenient but wrong — in the game such a call does not fire.
    """
    from pdxloc.core import qa_rules

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert "brackets_mismatch" in hoi4.check(
        "The University of [BRA.GetAdjective]", "[BRA.GetADjectiveCap]ий университет")


def test_an_ending_glued_to_a_word_is_not_a_missing_space():
    """«объявил[CHI.GetVerbGendEndA_RU]» is an ending, not a lost space."""
    from pdxloc.core import qa_rules

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert hoi4.check("[CHI.GetName] declared defense",
                      "[CHI.GetName] объявил[CHI.GetVerbGendEndA_RU] об обороне") == []
    # a substitution inside a word is a device as well: «анти[X.GetAdjective]ое»
    assert hoi4.check("Anti-[FROM.GetAdjective] Resistance",
                      "анти[FROM.GetAdjective]ое сопротивление") == []
    # while a space missed before a name stays a remark
    assert "glued_markup" in hoi4.check("in [350.GetName], today",
                                        "в регионе[350.GetName], сегодня")


def test_russian_ck2_inflects_with_functions_of_its_own():
    """«сража[X.GetLasLsya], [X.GetFirstName]» is a device, not a lost reference.

    The Russian CK2 declines with 259 functions of the game and adds an address
    where English has none. The built-in set counts both as an error: 45,593
    remarks on the vanilla translation against 24,047 under the preset.
    """
    from pdxloc.core import qa_rules

    en = "A worthy opponent, to the end..."
    ru = "Ты славно сража[combatant_1.GetLasLsya], [combatant_1.GetFirstName]."
    assert "brackets_mismatch" in check_unit(en, ru)

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert ck2.check(en, ru) == []


def test_ck2_preset_still_notices_a_lost_reference():
    """An added substitution does not break the game, a lost one leaves a hole."""
    from pdxloc.core import qa_rules

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert "brackets_mismatch" in ck2.check(
        "Honestly, [other_combatant.GetTitledFirstName]? Too easy.",
        "Ты просто ничтожество!")


def test_ck2_preset_does_not_forgive_a_typo_in_a_function_name():
    """`GeAdjective` and `GerHerHim` are live typos, and in the game they do not fire.

    The list of declining functions is picked by frequency: those met five times
    and more often. A typo does not reach that threshold — that is the intent.
    """
    from pdxloc.core import inflections, qa_rules

    assert "GetEndA" in inflections.CK2_RU_CALLS
    for typo in ("GeAdjective", "GerHerHim", "EndA"):
        assert typo not in inflections.CK2_RU_CALLS

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert "brackets_mismatch" in ck2.check(
        "He rides [Root.GetHerHis] horse", "Он оседла[Root.GeKaEts] коня")


def test_allow_extra_is_off_by_default():
    """The parameter is switched on by a preset: an extra reference happens to be an error too."""
    from pdxloc.core import qa_rules

    rule = qa_rules.default_ruleset().get("brackets_mismatch")
    assert rule.params["allow_extra"] is False
    assert "brackets_mismatch" in check_unit("Rules", "Правит [GetName]")


# --- Stellaris: the grammar inside the row -------------------------------


def test_grammar_mismatch_catches_a_lost_tag():
    """`Agrippa&!masc` → «Агриппа»: the name stops being masculine.

    In the official Russian translation of Stellaris there are 502 such rows.
    """
    assert "grammar_mismatch" in check_unit("Agrippa&!masc", "Агриппа")
    assert check_unit("Agrippa&!masc", "Агриппа&!masc") == []


def test_grammar_variants_added_by_the_translator_are_not_a_mismatch():
    """The variants for the cases are added by the translator — 6,327 rows against 463."""
    assert "grammar_mismatch" not in check_unit(
        "Queen", "Королева&!fem|||gen:Королевы")
    # while a lost variant of the original is a divergence
    assert "grammar_mismatch" in check_unit("A $1$|||vowel:An $1$", "$1$")


def test_stellaris_preset_lowers_the_names_that_match_the_original():
    """same_as_en stays switched on but stops shouting.

    17,156 hits on the vanilla pair — terms and names; the rule cannot be
    switched off, real untranslated text hides among them.
    """
    from pdxloc.core import qa_rules

    stellaris = qa_rules.resolve({"preset": "stellaris_ru"}, locale="ru")
    assert stellaris.get("same_as_en").enabled
    assert stellaris.severity("same_as_en") == qa_rules.INFO
    assert "same_as_en" in stellaris.check("Gestalt Consciousness", "Gestalt Consciousness")

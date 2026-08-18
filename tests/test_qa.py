"""Тесты QA-проверок: позитив/негатив на каждый код."""
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
    """Замер на живом переводе развёл два случая под одним кодом.

    789 срабатываний из 1413 — «в переводе не осталось ни одной переменной», то
    есть дыра в тексте прямо в игре; остальные 624 — набор отличается, а это
    чаще осознанная перестановка. Пресетом такое не лечится: правилу нужен свой
    параметр, и он выключен по умолчанию — замена бывает и ошибкой тоже.
    """
    from pdxloc.core import qa_rules

    strict = qa_rules.default_ruleset().restricted_to({"dollar_mismatch"})
    lenient = strict.with_rule(
        strict.get("dollar_mismatch").with_params(only_if_all_lost=True))

    assert strict.check("$A$ and $B$", "текст") == ["dollar_mismatch"]
    assert lenient.check("$A$ and $B$", "текст") == ["dollar_mismatch"]

    assert strict.check("$A$ and $B$", "$A$ текст") == ["dollar_mismatch"]
    assert lenient.check("$A$ and $B$", "$A$ текст") == []
    # и там, где переменных не было вовсе, послабление не выдумывает замечаний
    assert lenient.check("plain", "просто текст") == []


def test_icon_mismatch():
    assert "icon_mismatch" in check_unit("Pay £gold£", "Заплатить золотом")


def test_unclosed_tag_in_original_is_not_an_error():
    """Главный фикс v4: в CK3 тег в конце строки закрывать не обязательно.

    Прежнее правило требовало баланса #тегов и #! в переводе и давало
    826 ложных срабатываний из 827 на живом проекте.
    """
    en = "Some text.\\n#weak Words fade; writs remain."
    ru = "Некий текст.\\n#weak Слова тускнеют, записи остаются."
    assert check_unit(en, ru) == []


def test_fmt_broken_when_original_is_closed():
    """А вот если в оригинале тег закрыт, а в переводе нет — это ошибка."""
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
    """Регрессия: абзацный разрыв объявлялся опечаткой.

    Перенос строки в формате Paradox записан двумя символами — обратным слэшем
    и «n». Правило заменяло каждый такой перенос на пробел и потом искало два
    пробела подряд, поэтому любой абзацный разрыв `\\n\\n` выглядел как двойной
    пробел. На живом проекте так помечались 84 перевода из 4851 — все ложно.
    """
    assert "double_space" not in check_unit("Dawn.\\n\\nThen night.", "Рассвет.\\n\\nПотом ночь.")
    # пробел рядом с переносом — тоже не двойной пробел
    assert "double_space" not in check_unit("a\\nb", "а \\n б")


def test_double_space_still_caught():
    assert "double_space" in check_unit("Two words", "Два  слова")
    assert "double_space" in check_unit("a\\nb", "аа  бб\\nвв")
    # краевые пробелы — это отдельное замечание, не двойной пробел
    codes = check_unit("Text", "  текст")
    assert "edge_space" in codes and "double_space" not in codes


def test_empty_translated():
    assert check_unit("Text", "   ") == ["empty_translated"]


def test_same_as_en():
    assert "same_as_en" in check_unit("Same text here", "Same text here")


def test_len_ratio_disabled_by_default():
    """Эвристика длины шумит (208 срабатываний на живых данных) — по умолчанию выключена."""
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


# --- HOI4: цвет, склонения, пресет ---------------------------------------


def test_color_mismatch():
    assert "color_mismatch" in check_unit("§YWarning§!", "Внимание")
    assert "color_mismatch" in check_unit("§YWarning§!", "§RВнимание§!")   # цвет подменён
    assert check_unit("§YWarning§!", "§YВнимание§!") == []


def test_colour_from_a_script_call_is_a_colour_too():
    assert check_unit("§[GetColour]Text§!", "§[GetColour]Текст§!") == []
    assert "color_mismatch" in check_unit("§[GetColour]Text§!", "Текст")


def test_icon_named_by_a_variable_is_checked():
    assert check_unit("£$ICON$£ bonus", "£$ICON$£ бонус") == []
    assert "icon_mismatch" in check_unit("£$ICON$£ bonus", "бонус")


def test_russian_hoi4_inflection_is_a_technique_not_a_loss():
    """`[JAP.GetAdjective]` → `[JAP.GetAdjRuLower]ие` — приём самой игры.

    Встроенный набор считает это потерей ссылки (5 028 строк ванильного
    русского HOI4), пресет `hoi4_ru` — нет. Заменой прощается ровно один
    токен: настоящая потеря обязана остаться видимой.
    """
    from pdxloc.core import qa_rules

    en = "Cancel the [JAP.GetAdjective] rights in [655.GetName]"
    ru = "Отменить [JAP.GetAdjRuLower]ие права в регионе [655.GetName]"
    assert "brackets_mismatch" in check_unit(en, ru)

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert hoi4.check(en, ru) == []
    # потерянная вторая ссылка не прощается
    assert "brackets_mismatch" in hoi4.check(
        en, "Отменить [JAP.GetAdjRuLower]ие права")


def test_a_typo_in_a_function_name_is_not_forgiven():
    """`GetADjectiveCap` и `GetAdejctive` — живые опечатки ванильного перевода.

    Список склоняющих функций собран из тех, которых в английском дереве нет
    ни разу; опечатка тоже там не встречается, и прощать её было бы удобно, но
    неверно — в игре такой вызов не сработает.
    """
    from pdxloc.core import qa_rules

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert "brackets_mismatch" in hoi4.check(
        "The University of [BRA.GetAdjective]", "[BRA.GetADjectiveCap]ий университет")


def test_an_ending_glued_to_a_word_is_not_a_missing_space():
    """«объявил[CHI.GetVerbGendEndA_RU]» — окончание, а не потерянный пробел."""
    from pdxloc.core import qa_rules

    hoi4 = qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")
    assert hoi4.check("[CHI.GetName] declared defense",
                      "[CHI.GetName] объявил[CHI.GetVerbGendEndA_RU] об обороне") == []
    # подстановка внутри слова — тоже приём: «анти[X.GetAdjective]ое»
    assert hoi4.check("Anti-[FROM.GetAdjective] Resistance",
                      "анти[FROM.GetAdjective]ое сопротивление") == []
    # а вот пропущенный пробел перед именем остаётся замечанием
    assert "glued_markup" in hoi4.check("in [350.GetName], today",
                                        "в регионе[350.GetName], сегодня")


def test_russian_ck2_inflects_with_functions_of_its_own():
    """«сража[X.GetLasLsya], [X.GetFirstName]» — приём, а не потеря ссылки.

    Русская CK2 склоняет 259 функциями игры и дописывает обращение там, где
    по-английски его нет. Встроенный набор считает и то, и другое ошибкой:
    45 593 замечания на ванильном переводе против 24 047 под пресетом.
    """
    from pdxloc.core import qa_rules

    en = "A worthy opponent, to the end..."
    ru = "Ты славно сража[combatant_1.GetLasLsya], [combatant_1.GetFirstName]."
    assert "brackets_mismatch" in check_unit(en, ru)

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert ck2.check(en, ru) == []


def test_ck2_preset_still_notices_a_lost_reference():
    """Добавленная подстановка игру не ломает, потерянная — оставляет дыру."""
    from pdxloc.core import qa_rules

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert "brackets_mismatch" in ck2.check(
        "Honestly, [other_combatant.GetTitledFirstName]? Too easy.",
        "Ты просто ничтожество!")


def test_ck2_preset_does_not_forgive_a_typo_in_a_function_name():
    """`GeAdjective` и `GerHerHim` — живые опечатки, и в игре они не сработают.

    Список склоняющих функций отобран по частоте: встреченные пять раз и чаще.
    Опечатка в этот порог не попадает — на то и расчёт.
    """
    from pdxloc.core import inflections, qa_rules

    assert "GetEndA" in inflections.CK2_RU_CALLS
    for typo in ("GeAdjective", "GerHerHim", "EndA"):
        assert typo not in inflections.CK2_RU_CALLS

    ck2 = qa_rules.resolve({"preset": "ck2_ru"}, locale="ru")
    assert "brackets_mismatch" in ck2.check(
        "He rides [Root.GetHerHis] horse", "Он оседла[Root.GeKaEts] коня")


def test_allow_extra_is_off_by_default():
    """Параметр включается пресетом: лишняя ссылка бывает и ошибкой тоже."""
    from pdxloc.core import qa_rules

    rule = qa_rules.default_ruleset().get("brackets_mismatch")
    assert rule.params["allow_extra"] is False
    assert "brackets_mismatch" in check_unit("Rules", "Правит [GetName]")


# --- Stellaris: грамматика в строке --------------------------------------


def test_grammar_mismatch_catches_a_lost_tag():
    """`Agrippa&!masc` → «Агриппа»: имя перестанет быть мужского рода.

    В официальном русском переводе Stellaris таких 502 строки.
    """
    assert "grammar_mismatch" in check_unit("Agrippa&!masc", "Агриппа")
    assert check_unit("Agrippa&!masc", "Агриппа&!masc") == []


def test_grammar_variants_added_by_the_translator_are_not_a_mismatch():
    """Варианты для падежей дописывает переводчик — 6 327 строк против 463."""
    assert "grammar_mismatch" not in check_unit(
        "Queen", "Королева&!fem|||gen:Королевы")
    # а потерянный вариант оригинала — расхождение
    assert "grammar_mismatch" in check_unit("A $1$|||vowel:An $1$", "$1$")


def test_stellaris_preset_lowers_the_names_that_match_the_original():
    """same_as_en остаётся включённым, но перестаёт кричать.

    17 156 срабатываний на ванильной паре — термины и названия; выключить
    правило нельзя, среди них прячется и настоящий непереведённый текст.
    """
    from pdxloc.core import qa_rules

    stellaris = qa_rules.resolve({"preset": "stellaris_ru"}, locale="ru")
    assert stellaris.get("same_as_en").enabled
    assert stellaris.severity("same_as_en") == qa_rules.INFO
    assert "same_as_en" in stellaris.check("Gestalt Consciousness", "Gestalt Consciousness")

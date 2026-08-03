"""Тесты QA-проверок: позитив/негатив на каждый код."""
from __future__ import annotations

from ck3loc.core.qa import check_unit, strip_markup


def test_ok_translation_no_issues():
    en = 'Gain #bold [GetTrait(\'brave\').GetName]#! and $VALUE$ £gold£'
    ru = 'Получить #bold [GetTrait(\'brave\').GetName]#! и $VALUE$ £gold£'
    assert check_unit(en, ru) == []


def test_dollar_mismatch():
    assert "dollar_mismatch" in check_unit("Cost: $VALUE$", "Цена: непонятно")
    assert "dollar_mismatch" not in check_unit("Cost: $VALUE$", "Цена: $VALUE$")


def test_dollar_with_format_pipe():
    assert check_unit("Bonus $VAL|=+0$", "Бонус $VAL|=+0$") == []


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

"""Реестр правил обязан повторять прежнее поведение проверки.

Проверки переехали из тела `check_unit` в таблицу правил с параметрами. Сам по
себе переезд не должен изменить ни одного вердикта: смена дефолтов делается
отдельно и подтверждается замером на живых данных.

Корпус собран из каверзных случаев, ради которых писались прежние тесты, —
если реестр где-то соврёт, упадёт именно здесь, а не в живом проекте через
неделю.

Два дефолта с тех пор изменены осознанно (`edge_space.compare_with_source`,
`unbalanced_quotes.only_if_source_balanced`) — они только гасят срабатывания;
что ни одного нового при этом не появляется, проверяет `test_qa_defaults.py`.
"""
from __future__ import annotations

import pytest

from pdxloc.core import qa, qa_rules

TRAIT = "[GetTrait('loyal').GetName( GetNullCharacter )]"

# (оригинал, перевод, ожидаемые коды) — ожидания сняты с поведения ДО реестра
CORPUS: tuple[tuple[str, str, list[str]], ...] = (
    # чистые строки
    ("Hello", "Привет", []),
    ("Cost: $VALUE|=+0$ £gold£", "Цена: $VALUE|=+0$ £gold£", []),
    ("#bold Text#!", "#bold Текст#!", []),
    ("[GetName] rules", "[GetName] правит", []),
    ("One\\ntwo", "Один\\nдва", []),
    ("A (b) c", "А (б) в", []),
    # пустой перевод обрывает разбор — остальных замечаний быть не должно
    ("Text", "", ["empty_translated"]),
    ("Text", "   ", ["empty_translated"]),
    # разметка
    ("Cost: $VALUE$", "Цена", ["dollar_mismatch"]),
    ("£gold£ paid", "уплачено", ["icon_mismatch"]),
    ("@gold! paid", "уплачено", ["icon_mismatch"]),
    ("@gold! paid", "@gold! уплачено", []),
    # тег с параметром: fmt_open по-прежнему видит голову и не начинает ругаться
    ("#indent_newline:2 Text", "#indent_newline:2 Текст", []),
    ("#TOOLTIP:hint Text", "#TOOLTIP:hint Текст", []),
    ("Rules [GetName]", "Правит", ["brackets_mismatch"]),
    ("One\\ntwo", "Один два", ["newline_mismatch"]),
    # оформление
    ("#bold Text#!", "Текст", ["fmt_mismatch"]),
    ("#bold Text#!", "#bold Текст", ["fmt_broken"]),
    ("#weak Text", "#weak Текст", []),          # оригинал не закрыт — не ошибка
    ("#high;italic T#!", "#high;italic Т#!", []),
    # типографика
    ("Hello", "Hello", ["same_as_en"]),
    ("Hello", "Привет ", ["edge_space"]),
    ("Hello world", "Привет  мир", ["double_space"]),
    ("Hello\\n\\nworld", "Привет\\n\\nмир", []),    # абзац — не двойной пробел
    ("A (b) c", "А (б в", ["unbalanced_quotes"]),
    # русский язык
    ("House [GetPlayer.GetDynasty.GetName]",
     "дома[GetPlayer.GetDynasty.GetName]", ["glued_markup"]),
    ("House [GetPlayer.GetDynasty.GetName]",
     "дома [GetPlayer.GetDynasty.GetName]", []),
    # склейка окончания законна и не ловится как glued_markup; про лишнюю
    # скобку правило пока ругается — это тот самый шум, который чинят параметры
    ("[X.GetSheHe|U] granted",
     "[X.GetSheHe|U] даровал[Select_CString(X.IsFemale, 'а', '')]",
     ["brackets_mismatch"]),
    ("closer to [target.GetHerHim]", "ближе к н[target.GetHerHim]", []),
    (f"Beesburys tend to be {TRAIT}", f"Бисбери склонны быть {TRAIT}",
     ["linking_calque"]),
    (f"Beesburys tend to be {TRAIT}",
     f"Бисбери склонны проявлять черту: {TRAIT}", []),
    ("the scheme targeting [TARGET.GetShortUIName]",
     "происки, целью которых является [TARGET.GetShortUIName]", []),
)


@pytest.mark.parametrize("en,ru,expected", CORPUS,
                         ids=[f"{i:02d}" for i in range(len(CORPUS))])
def test_default_behaviour_is_unchanged(en: str, ru: str, expected: list[str]) -> None:
    assert qa.check_unit(en, ru) == expected


def test_len_ratio_stays_off_by_default() -> None:
    long_en = "A reasonably long English sentence goes here"
    assert "len_ratio" not in qa.check_unit(long_en, "Коротко")


def test_len_ratio_fires_when_asked() -> None:
    long_en = "A reasonably long English sentence goes here"
    assert qa.check_unit(long_en, "Коротко", enabled={"len_ratio"}) == ["len_ratio"]


def test_enabled_narrows_the_set_strictly() -> None:
    """Старый контракт: перечислили один код — получили только его."""
    en, ru = "Hello world", "Привет  мир "
    assert qa.check_unit(en, ru, enabled={"double_space"}) == ["double_space"]
    assert set(qa.check_unit(en, ru)) == {"double_space", "edge_space"}


def test_codes_dictionary_still_describes_every_rule() -> None:
    """По qa.CODES ходят окно отчёта и колонка «!» — она обязана быть полной."""
    assert set(qa.CODES) == {r.id for r in qa_rules.BUILTIN_RULES}
    for severity, message in qa.CODES.values():
        assert severity in qa_rules.SEVERITIES
        assert message


def test_optional_codes_match_disabled_rules() -> None:
    assert {"len_ratio"} == qa.OPTIONAL_CODES


# --- параметры заведены и работают --------------------------------------


def rule_with(code: str, **params) -> qa_rules.RuleSet:
    rules = qa_rules.default_ruleset()
    return rules.with_rule(rules.get(code).with_params(**params))


def test_brackets_can_forgive_a_grammar_wrapper() -> None:
    """Обёртка ради склонения — приём, а не потеря ссылки."""
    en, ru = "Dusk King", "[Select_CString(CHARACTER.IsFemale, 'Королева', 'Король')]"
    assert qa.check_unit(en, ru) == ["brackets_mismatch"]
    quiet = rule_with("brackets_mismatch", ignore_extra_heads=["Select_CString"])
    assert qa.check_unit(en, ru, ruleset=quiet) == []


def test_brackets_can_forgive_a_wrapper_used_instead_of_a_reference() -> None:
    """Замена подстановки на грамматическую обёртку — 59% всего шума по скобкам.

    Английское [CharAreIs(actor)] по-русски требует рода, и переводчик ставит
    вместо него [Select_CString(actor.IsFemale, 'ведьма', 'колдун')].
    """
    en = "[CharAreIs(actor)] a witch"
    ru = "[Select_CString(actor.IsFemale, 'известная ведьма', 'известный колдун')]"
    assert qa.check_unit(en, ru) == ["brackets_mismatch"]

    swap = rule_with("brackets_mismatch",
                     ignore_extra_heads=["Select_CString"], allow_replacement=True)
    assert qa.check_unit(en, ru, ruleset=swap) == []

    # но настоящая потеря ссылки прощаться не должна: обёрток нет, гасить нечем
    assert qa.check_unit("Rules [GetName] here", "Правит здесь", ruleset=swap) == \
        ["brackets_mismatch"]


def test_replacement_budget_is_one_for_one() -> None:
    """Прощаем столько потерь, сколько добавлено обёрток, — не больше."""
    swap = rule_with("brackets_mismatch",
                     ignore_extra_heads=["Select_CString"], allow_replacement=True)
    en = "[A] [B] [C]"
    ru = "[Select_CString(x.IsFemale, 'а', 'б')] [B]"    # одна обёртка, две потери
    assert qa.check_unit(en, ru, ruleset=swap) == ["brackets_mismatch"]


def test_brackets_can_ignore_flags() -> None:
    en, ru = "see [men_at_arms|E]", "см. [men_at_arms|El]"
    assert qa.check_unit(en, ru) == ["brackets_mismatch"]
    quiet = rule_with("brackets_mismatch", ignore_flags=True)
    assert qa.check_unit(en, ru, ruleset=quiet) == []


def test_format_can_allow_an_extra_tag() -> None:
    """Переводчик дописывает #L ради падежа — это приём."""
    en, ru = "[X.GetAdjective] war", "#L [X.GetAdjective]ая#! война"
    assert "fmt_mismatch" in qa.check_unit(en, ru)
    quiet = rule_with("fmt_mismatch", allow_extra_tags=["#L"])
    assert "fmt_mismatch" not in qa.check_unit(en, ru, ruleset=quiet)


def test_format_can_ignore_tag_case() -> None:
    en, ru = "#bold Text#!", "#BOLD Текст#!"
    assert "fmt_mismatch" in qa.check_unit(en, ru)
    quiet = rule_with("fmt_mismatch", case_insensitive=True)
    assert "fmt_mismatch" not in qa.check_unit(en, ru, ruleset=quiet)


def test_edge_space_compares_with_source_by_default() -> None:
    """Краевой пробел бывает и в оригинале — так склеивают строки в игре."""
    en, ru = "Hello ", "Привет "
    assert "edge_space" not in qa.check_unit(en, ru)
    # а вот пробел, которого в оригинале не было, ловится по-прежнему
    assert "edge_space" in qa.check_unit("Hello", "Привет ")
    strict = rule_with("edge_space", compare_with_source=False)
    assert "edge_space" in qa.check_unit(en, ru, ruleset=strict)


def test_quotes_forgive_an_unbalanced_source_by_default() -> None:
    en, ru = 'He said "hello', 'Он сказал "привет'
    assert "unbalanced_quotes" not in qa.check_unit(en, ru)
    # оригинал сбалансирован — за перевод отвечает переводчик
    assert "unbalanced_quotes" in qa.check_unit('He said "hello"', 'Он сказал "привет')
    strict = rule_with("unbalanced_quotes", only_if_source_balanced=False)
    assert "unbalanced_quotes" in qa.check_unit(en, ru, ruleset=strict)


def test_newline_can_watch_only_losses() -> None:
    quiet = rule_with("newline_mismatch", direction="fewer")
    assert "newline_mismatch" in qa.check_unit("a\\nb", "а б", ruleset=quiet)
    assert "newline_mismatch" not in qa.check_unit("a b", "а\\nб", ruleset=quiet)


def test_calque_verbs_are_editable() -> None:
    """Чаще нужно расширить готовое правило, чем написать новое."""
    en, ru = f"They appear {TRAIT}", f"Они выглядят {TRAIT}"
    assert qa.check_unit(en, ru) == []
    wider = rule_with("linking_calque",
                      verbs=[*list(qa_rules.CALQUE_VERBS), "выглядят"])
    assert qa.check_unit(en, ru, ruleset=wider) == ["linking_calque"]


def test_disabling_a_rule_silences_it() -> None:
    rules = qa_rules.default_ruleset()
    off = rules.with_rule(
        qa_rules.replace(rules.get("brackets_mismatch"), enabled=False))
    assert qa.check_unit("Rules [GetName]", "Правит", ruleset=off) == []

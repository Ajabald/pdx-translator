"""Свои правила проверки: шесть декларативных видов и их хранение.

Главное свойство, ради которого виды сделаны именно такими: **чужое правило —
данные, а не код**. Оно приезжает из файла проекта, из глобальной настройки и из
файла обмена, и любое из трёх мест может оказаться написанным другой версией
приложения или просто испорченным. Ни один такой случай не имеет права ни
уронить проход по сотне тысяч строк, ни подменить встроенную проверку.
"""
from __future__ import annotations

import json

import pytest

from pdxloc.core import qa_rules


def rule(kind: str, **params):
    return qa_rules.make_user_rule("own", kind, title="Своё", params=params)


def check(rule_obj, en: str, ru: str) -> list[str]:
    return qa_rules.RuleSet([rule_obj]).check(en, ru)


# --- шесть видов ---------------------------------------------------------


CASES = [
    # (вид, параметры, оригинал, перевод-с-ошибкой, перевод-без-ошибки)
    # мультимножество — для того, что обязано остаться дословно; счёт — для
    # того, что переводится, и совпадать может только числом
    ("token_multiset", {"pattern": r"%\w+%"},
     "Hi %NAME%", "Привет", "Привет, %NAME%"),
    ("token_count", {"pattern": "«[^»]*»"},
     "«A» and «B»", "«А»", "«А» и «Б»"),
    ("target_regex", {"pattern": "  +"},
     "Hello world", "Привет  мир", "Привет мир"),
    ("target_regex", {"pattern": r"\d", "mode": "require"},
     "5 gold", "золото", "5 золота"),
    ("pair_regex", {"source": r"\$(\w+)\$", "target": r"$\1$"},
     "Cost: $VALUE$", "Цена", "Цена: $VALUE$"),
    ("balance", {"pairs": ["«»"]},
     "A quote", "«Цитата", "«Цитата»"),
    ("forbidden_chars", {"chars": "…"},
     "Wait...", "Подожди…", "Подожди..."),
]


@pytest.mark.parametrize("kind,params,en,bad,ok", CASES)
def test_kind_fires_and_stays_silent(kind, params, en, bad, ok) -> None:
    own = rule(kind, **params)
    assert check(own, en, bad) == ["own"]
    assert check(own, en, ok) == []


def test_every_kind_is_described_and_has_a_check() -> None:
    """Вид без подписи невозможно выбрать, вид без проверки молчит всегда."""
    for kind_id in qa_rules.KIND_ORDER:
        kind = qa_rules.KINDS[kind_id]
        assert kind.title and kind.hint
        assert callable(kind.check)


def test_count_direction_ignores_extra_matches() -> None:
    own = rule("token_count", pattern=r"\d+", direction="fewer")
    assert check(own, "1 2", "1") == ["own"]
    assert check(own, "1", "1 2") == []


def test_pair_regex_answer_is_plain_text_by_default() -> None:
    """`$\\1$` в роли выражения означал бы «конец строки» и не нашёл бы ничего."""
    own = rule("pair_regex", source=r"\$(\w+)\$", target=r"$\1$")
    assert check(own, "Cost: $GOLD$", "Цена: $GOLD$") == []


def test_pair_regex_survives_a_template_without_a_group() -> None:
    own = rule("pair_regex", source=r"\$\w+\$", target=r"$\3$")
    assert check(own, "Cost: $GOLD$", "Цена") == []


def test_balance_counts_identical_halves_by_parity() -> None:
    """Для «"» равенство счётчиков выполняется всегда и не значит ничего."""
    own = rule("balance", pairs=['""'])
    assert check(own, "plain", 'Он сказал "да') == ["own"]
    assert check(own, "plain", 'Он сказал "да"') == []


def test_forbidden_chars_can_forgive_the_original() -> None:
    own = rule("forbidden_chars", chars="…", ignore_if_in_source=True)
    assert check(own, "Wait…", "Подожди…") == []
    assert check(own, "Wait...", "Подожди…") == ["own"]


def test_groups_in_the_pattern_do_not_change_what_is_counted() -> None:
    """`findall` отдал бы группы вместо совпадений, и правило поменяло бы смысл."""
    with_group = rule("token_multiset", pattern=r"%(\w+)%")
    without = rule("token_multiset", pattern=r"%\w+%")
    en, ru = "%NAME%", "%ИМЯ%"
    assert check(with_group, en, ru) == check(without, en, ru) == ["own"]


# --- битое выражение ------------------------------------------------------


@pytest.mark.parametrize("kind,params", [
    ("token_multiset", {"pattern": "([a-z"}),
    ("token_count", {"pattern": "([a-z"}),
    ("target_regex", {"pattern": "([a-z"}),
    ("pair_regex", {"source": "([a-z"}),
])
def test_broken_expression_silences_only_its_own_rule(kind, params) -> None:
    """Падать посреди прохода по проекту из-за чужой опечатки нельзя."""
    own = rule(kind, **params)
    rules = qa_rules.with_user_rules(qa_rules.default_ruleset(), [own])
    codes = rules.check("Cost: $V$", "Цена")
    assert "own" not in codes
    assert "dollar_mismatch" in codes        # остальные работают как работали


def test_empty_expression_is_not_an_error_yet() -> None:
    """Правило только что заведено — ругаться на каждую строку оно не должно."""
    assert check(rule("token_multiset"), "a", "b") == []
    assert check(rule("target_regex"), "a", "b") == []


def test_a_broken_parameter_silences_its_rule_not_the_whole_pass() -> None:
    """Опечатка в числе гасит своё правило, а не проход по сотне тысяч строк.

    `qa_rules.json` носят между машинами, `.pdxqa` пересылают друг другу — оба
    файла правят руками, ради этого они и заведены. Значение не того типа
    доезжает до `int()` уже внутри проверки; раньше это роняло всю проверку
    целиком, вместе с колонкой замечаний и отчётом F6.
    """
    broken = qa_rules.apply_delta(
        qa_rules.default_ruleset(),
        {"glued_markup": {"params": {"min_word_len": "три"}}})

    codes = broken.check("Hi $NAME$", "Привет")

    assert "dollar_mismatch" in codes       # соседние правила работают
    assert "glued_markup" not in codes      # сломанное молчит


def test_regex_error_tells_what_is_wrong() -> None:
    assert qa_rules.regex_error("([a-z")
    assert qa_rules.regex_error(r"\d+") == ""
    assert qa_rules.regex_error("") == ""


def test_a_pattern_that_can_hang_the_check_is_flagged() -> None:
    """Повтор внутри повторяемой группы — экспоненциальный перебор.

    Прервать `re` нечем: таймаута у него нет, а сигналы на Windows не работают.
    Значит единственная защита — сказать об этом в окне правил, до того как
    проверка пойдёт по сотне тысяч строк. Правила ещё и ездят между людьми
    файлом `.pdxqa`, так что предупреждение нужно и для чужого правила.
    """
    assert qa_rules.regex_warning(r"(\w+)+$")
    assert qa_rules.regex_warning(r"(a*)*")
    assert qa_rules.regex_warning(r"(\d+\s?)+")

    # обычные выражения молчат
    assert qa_rules.regex_warning(r"\d+") == ""
    assert qa_rules.regex_warning(r"(?:\w+)\s*") == ""
    assert qa_rules.regex_warning(r"\[[^\]]+\]") == ""
    assert qa_rules.regex_warning("") == ""
    # битое выражение — забота regex_error, здесь молчим
    assert qa_rules.regex_warning("([a-z") == ""


# --- чтение чужой записи --------------------------------------------------


def test_user_rule_cannot_shadow_a_builtin_check() -> None:
    """Иначе чужой файл подменил бы проверку скобок своим выражением."""
    assert qa_rules.load_user_rule(
        {"id": "brackets_mismatch", "kind": "target_regex", "title": "x"}) is None


@pytest.mark.parametrize("record", [
    {"id": "x", "kind": "такого_вида_нет", "title": "x"},
    {"id": "", "kind": "target_regex", "title": "x"},
    {"kind": "target_regex", "title": "x"},
    "не запись вовсе",
])
def test_unreadable_record_is_skipped(record) -> None:
    assert qa_rules.load_user_rule(record) is None


def test_unknown_params_and_categories_do_not_travel() -> None:
    loaded = qa_rules.load_user_rule({
        "id": "x", "kind": "forbidden_chars", "title": "x",
        "category": "такой_категории_нет",
        "params": {"chars": "…", "такого_нет": 1},
    })
    assert "такого_нет" not in loaded.params
    assert loaded.params["chars"] == "…"
    # незнакомая категория увела бы правило из дерева окна целиком
    assert loaded.category in qa_rules.CATEGORIES


def test_unknown_severity_falls_back_to_warning() -> None:
    loaded = qa_rules.load_user_rule(
        {"id": "x", "kind": "forbidden_chars", "title": "x", "severity": "кошмар"})
    assert loaded.severity == qa_rules.WARNING


# --- хранение в оверлее ---------------------------------------------------


def test_user_rule_is_stored_whole_and_restored() -> None:
    own = rule("forbidden_chars", chars="…")
    rules = qa_rules.with_user_rules(qa_rules.default_ruleset(), [own])
    overlay = json.loads(json.dumps(
        qa_rules.make_overlay(qa_rules.CUSTOM, rules), ensure_ascii=False))

    restored = qa_rules.resolve(overlay)
    assert restored.get("own").params["chars"] == "…"
    assert restored.check("Wait...", "Подожди…") == ["own"]


def test_project_layer_does_not_copy_a_global_user_rule() -> None:
    """Правило заведено на все проекты — жить оно должно там же."""
    own = rule("forbidden_chars", chars="…")
    glob = qa_rules.make_overlay(qa_rules.CUSTOM,
                                 qa_rules.with_user_rules(
                                     qa_rules.default_ruleset(), [own]))
    rules = qa_rules.resolve(glob)
    project = qa_rules.make_overlay(qa_rules.CUSTOM, rules, under=glob)
    assert "custom" not in project
    assert project["rules"] == {}


def test_editing_a_global_user_rule_in_a_project_is_a_delta() -> None:
    own = rule("forbidden_chars", chars="…")
    glob = qa_rules.make_overlay(qa_rules.CUSTOM,
                                 qa_rules.with_user_rules(
                                     qa_rules.default_ruleset(), [own]))
    rules = qa_rules.resolve(glob)
    edited = rules.with_rule(qa_rules.replace(rules.get("own"), enabled=False))
    project = qa_rules.make_overlay(qa_rules.CUSTOM, edited, under=glob)
    assert project["rules"] == {"own": {"enabled": False}}
    assert not qa_rules.resolve(glob, project).get("own").enabled


def test_project_user_rule_replaces_the_global_one_whole() -> None:
    glob = qa_rules.make_overlay(
        qa_rules.CUSTOM,
        qa_rules.with_user_rules(qa_rules.default_ruleset(),
                                 [rule("forbidden_chars", chars="…")]))
    project = {"custom": [qa_rules.dump_user_rule(
        qa_rules.make_user_rule("own", "forbidden_chars", title="Своё",
                                params={"chars": "—"}))]}
    rules = qa_rules.resolve(glob, project)
    assert rules.get("own").params["chars"] == "—"
    assert len([r for r in rules if r.id == "own"]) == 1


def test_junk_custom_records_do_not_make_an_overlay_worth_storing() -> None:
    assert qa_rules.is_empty_overlay({"custom": [{"id": "x"}]})
    assert not qa_rules.is_empty_overlay(
        {"custom": [{"id": "x", "kind": "forbidden_chars", "title": "x"}]})


def test_user_rule_of_another_language_is_switched_off_not_dropped() -> None:
    """Как и у встроенных языковых правил: видно в окне, включается руками."""
    own = qa_rules.make_user_rule("own", "forbidden_chars", title="Своё",
                                  locale="ru", params={"chars": "…"})
    overlay = {"custom": [qa_rules.dump_user_rule(own)]}
    rules = qa_rules.resolve(overlay, locale="fr")
    assert rules.get("own") is not None
    assert not rules.get("own").enabled
    assert qa_rules.resolve(overlay, locale="ru").get("own").enabled

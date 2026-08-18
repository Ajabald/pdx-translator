"""Смена дефолтов обязана только гасить срабатывания.

Два параметра переведены в положение «сравнивать с оригиналом»:
`edge_space.compare_with_source` и `unbalanced_quotes.only_if_source_balanced`.
Повод — замер на живом переводе agoot: 93% и 74% срабатываний приходились на
пробел и кавычку, стоящие в самом оригинале.

Опасность у такой правки ровно одна: новый дефолт может не только убрать
лишнее, но и добавить срабатывание там, где его не было, — и переводчик
получит поток замечаний на ровном месте. Поэтому проверка не «стало меньше»,
а строгая: множество кодов при новых дефолтах — подмножество прежнего, на
каждой паре корпуса.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from pdxloc.core import qa, qa_rules

# Прежние значения — то, с чем правила жили до смены
OLD_DEFAULTS = {
    "edge_space": {"compare_with_source": False},
    "unbalanced_quotes": {"only_if_source_balanced": False},
}

# Пары, на которых эти правила вообще способны сработать: краевые пробелы,
# кавычки и скобки во всех сочетаниях «есть в оригинале / нет в оригинале».
CORPUS: tuple[tuple[str, str], ...] = (
    ("Hello", "Привет"),
    ("Hello", "Привет "),
    ("Hello", " Привет"),
    ("Hello ", "Привет "),
    ("Hello ", "Привет"),
    (" Hello", " Привет"),
    ("Hello\\n", "Привет\\n "),
    ('He said "hello"', 'Он сказал "привет"'),
    ('He said "hello"', 'Он сказал "привет'),
    ('He said "hello', 'Он сказал "привет'),
    ('He said "hello', 'Он сказал "привет"'),
    ("A (b) c", "А (б) в"),
    ("A (b) c", "А (б в"),
    ("A (b c", "А (б в"),
    ("A (b c", "А (б) в"),
    ("«Quote»", "«Цитата»"),
    ("«Quote»", "«Цитата"),
    ("[GetName] rules ", "[GetName] правит "),
    ("Cost: $V$ ", "Цена: $V$"),
)


def old_ruleset() -> qa_rules.RuleSet:
    rules = qa_rules.default_ruleset()
    for code, params in OLD_DEFAULTS.items():
        rules = rules.with_rule(rules.get(code).with_params(**params))
    return rules


@pytest.mark.parametrize("en,ru", CORPUS, ids=[f"{i:02d}" for i in range(len(CORPUS))])
def test_new_defaults_never_add_a_complaint(en: str, ru: str) -> None:
    before = set(qa.check_unit(en, ru, ruleset=old_ruleset()))
    after = set(qa.check_unit(en, ru))
    assert after <= before, f"новый дефолт добавил замечание: {after - before}"


def test_new_defaults_actually_remove_something() -> None:
    """Иначе правка была бы бессмысленной, а тест выше — тавтологией."""
    removed = set()
    for en, ru in CORPUS:
        removed |= (set(qa.check_unit(en, ru, ruleset=old_ruleset()))
                    - set(qa.check_unit(en, ru)))
    assert removed == set(OLD_DEFAULTS)


def test_every_rule_agrees_with_its_own_examples() -> None:
    """Пример ошибки обязан срабатывать, пример нормы — молчать.

    Дефолт меняют ради тишины, и легко доехать до правила, которое молчит
    всегда. Примеры внутри правил — его же самопроверка.
    """
    rules = qa_rules.default_ruleset()
    for rule in rules:
        single = rules.restricted_to({rule.id})
        for en, ru in rule.example_bad:
            assert single.check(en, ru) == [rule.id], f"{rule.id}: {en!r} → {ru!r}"
        for en, ru in rule.example_ok:
            assert single.check(en, ru) == [], f"{rule.id}: {en!r} → {ru!r}"


def test_severity_of_a_rule_can_be_lowered_to_a_signal() -> None:
    """`info` заведена ради `inconsistent`: это повод свериться, не ошибка."""
    rules = qa_rules.default_ruleset()
    quiet = rules.with_rule(
        replace(rules.get("inconsistent"), severity=qa_rules.INFO))
    assert quiet.severity("inconsistent") == qa_rules.INFO
    assert qa_rules.SEVERITY_RANK[qa_rules.INFO] > qa_rules.SEVERITY_RANK[
        qa_rules.WARNING]

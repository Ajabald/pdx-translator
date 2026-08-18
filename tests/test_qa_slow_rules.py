"""Своё правило, съевшее время, гаснет до конца прохода.

Повод — катастрофический бэктрекинг: `(\\w+)+$` на длинной строке считается
минутами, а проход идёт по сотне тысяч строк. Полностью это не лечится (см.
`SLOW_RULE_SECONDS`), но одно медленное правило не должно стоить всего прохода.
"""
from __future__ import annotations

from pdxloc.core import qa_rules
from pdxloc.core.qa_rules import BUILTIN, USER, Rule, RuleSet


def slow_rule(rule_id: str = "slow", *, origin: str = USER) -> Rule:
    """Правило, которое честно тратит больше порога на каждой строке."""
    import time

    def check(en, ru, params):
        time.sleep(qa_rules.SLOW_RULE_SECONDS * 1.2)
        return True

    # kind=BUILTIN — чтобы проверка бралась из CHECKS по имени правила;
    # origin решает, чьё правило, и именно его смотрит сторож времени
    rule = Rule(id=rule_id, title="Медленное", category="custom",
                severity="warning", message="медленное",
                kind=BUILTIN, origin=origin)
    qa_rules.CHECKS[rule_id] = check
    return rule


def fast_rule(rule_id: str = "fast") -> Rule:
    qa_rules.CHECKS[rule_id] = lambda en, ru, params: True
    return Rule(id=rule_id, title="Быстрое", category="custom",
                severity="warning", message="быстрое",
                kind=BUILTIN, origin=USER)


def teardown_function() -> None:
    for rule_id in ("slow", "fast", "slow_builtin"):
        qa_rules.CHECKS.pop(rule_id, None)


def test_a_slow_user_rule_stops_after_the_first_row() -> None:
    rules = RuleSet([slow_rule(), fast_rule()])

    assert "slow" in rules.check("Hello", "Привет")     # первый раз ещё работает
    assert "slow" in rules.exhausted

    # на следующей строке его уже не зовут, а соседнее правило цело
    found = rules.check("World", "Мир")
    assert "slow" not in found
    assert "fast" in found


def test_a_fresh_pass_starts_with_a_clean_slate() -> None:
    """Правило могло споткнуться об одну строку из ста тысяч.

    Наказывать его навсегда не за что: набор живёт ровно один проход.
    """
    first = RuleSet([slow_rule()])
    first.check("Hello", "Привет")
    assert first.exhausted

    second = RuleSet([slow_rule()])
    assert second.exhausted == set()


def test_a_builtin_rule_is_never_silenced() -> None:
    """Встроенные гасить нельзя: их проверку писал автор, и медленная встроенная
    проверка — это ошибка в приложении, а не в чужой настройке. Замолчать о ней
    значило бы спрятать собственную поломку.
    """
    rules = RuleSet([slow_rule("slow_builtin", origin=BUILTIN)])
    rules.check("Hello", "Привет")
    rules.check("World", "Мир")
    assert rules.exhausted == set()


def test_time_is_measured_even_for_rules_that_behave() -> None:
    """Счётчик нужен и быстрым — по нему видно, кто съел проход."""
    rules = RuleSet([fast_rule()])
    rules.check("Hello", "Привет")
    assert rules.spent["fast"] >= 0.0
    assert "fast" in rules.spent


def test_the_guard_does_not_touch_the_default_set() -> None:
    """Полсекунды на строку — на три порядка больше честного правила.

    Проверка от ложного срабатывания: весь встроенный набор на живой паре
    должен уложиться в порог с огромным запасом.
    """
    rules = qa_rules.default_ruleset()
    long_line = "The quick brown fox jumps over the lazy dog. " * 40
    rules.check(long_line, long_line)
    assert rules.exhausted == set()
    assert max(rules.spent.values()) < qa_rules.SLOW_RULE_SECONDS

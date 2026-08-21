"""A rule of one's own that has eaten time goes out for the rest of the pass.

The reason is catastrophic backtracking: `(\\w+)+$` on a long row is computed for
minutes, while a pass goes over a hundred thousand rows. This is not cured
completely (see `SLOW_RULE_SECONDS`), but one slow rule must not cost the whole pass.
"""
from __future__ import annotations

from pdxloc.core import qa_rules
from pdxloc.core.qa_rules import BUILTIN, USER, Rule, RuleSet


def slow_rule(rule_id: str = "slow", *, origin: str = USER) -> Rule:
    """A rule that honestly spends more than the threshold on every row."""
    import time

    def check(en, ru, params):
        time.sleep(qa_rules.SLOW_RULE_SECONDS * 1.2)
        return True

    # kind=BUILTIN — so that the check is taken out of CHECKS by the name of the
    # rule; origin decides whose rule it is, and that is what the time guard looks at
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

    assert "slow" in rules.check("Hello", "Привет")     # the first time it still works
    assert "slow" in rules.exhausted

    # on the next row it is no longer called, while the neighbouring rule is intact
    found = rules.check("World", "Мир")
    assert "slow" not in found
    assert "fast" in found


def test_a_fresh_pass_starts_with_a_clean_slate() -> None:
    """The rule may have stumbled over one row out of a hundred thousand.

    There is nothing to punish it forever for: a set lives exactly one pass.
    """
    first = RuleSet([slow_rule()])
    first.check("Hello", "Привет")
    assert first.exhausted

    second = RuleSet([slow_rule()])
    assert second.exhausted == set()


def test_a_builtin_rule_is_never_silenced() -> None:
    """The built-in ones must not be quieted: their check was written by the author,
    and a slow built-in check is an error in the application and not in somebody
    else's setting. To fall silent about it would mean hiding our own breakage.
    """
    rules = RuleSet([slow_rule("slow_builtin", origin=BUILTIN)])
    rules.check("Hello", "Привет")
    rules.check("World", "Мир")
    assert rules.exhausted == set()


def test_time_is_measured_even_for_rules_that_behave() -> None:
    """The counter is needed for the fast ones too — it shows who ate the pass."""
    rules = RuleSet([fast_rule()])
    rules.check("Hello", "Привет")
    assert rules.spent["fast"] >= 0.0
    assert "fast" in rules.spent


def test_the_guard_does_not_touch_the_default_set() -> None:
    """Half a second per row is three orders of magnitude more than an honest rule.

    A check against a false hit: the whole built-in set on a live pair has to fit
    into the threshold with enormous room to spare.
    """
    rules = qa_rules.default_ruleset()
    long_line = "The quick brown fox jumps over the lazy dog. " * 40
    rules.check(long_line, long_line)
    assert rules.exhausted == set()
    assert max(rules.spent.values()) < qa_rules.SLOW_RULE_SECONDS

"""The examples inside the rules are a working self-check, not a decoration.

The device is borrowed from LanguageTool, where every rule is obliged to carry an
example of a hit and an example of silence. The use is double: in the rules window
they show what a rule does at all, and here they do not let a rule break quietly
at an edit of the parameters.
"""
from __future__ import annotations

import pytest

from pdxloc.core import qa, qa_rules

RULES = qa_rules.BUILTIN_RULES
IDS = [r.id for r in RULES]


def only(code: str) -> qa_rules.RuleSet:
    """A set of one rule — so that the example checks exactly it."""
    return qa_rules.default_ruleset().restricted_to({code})


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_every_rule_carries_examples(rule: qa_rules.Rule) -> None:
    if rule.id in qa_rules.PROJECT_WIDE:
        pytest.skip("проверке нужен весь проект, парой строк её не показать")
    assert rule.example_bad, f"{rule.id}: нет примера срабатывания"
    assert rule.example_ok, f"{rule.id}: нет примера молчания"


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_bad_examples_do_fire(rule: qa_rules.Rule) -> None:
    for en, ru in rule.example_bad:
        assert rule.id in qa.check_unit(en, ru, ruleset=only(rule.id)), \
            f"{rule.id}: пример срабатывания молчит — {en!r} / {ru!r}"


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_ok_examples_stay_silent(rule: qa_rules.Rule) -> None:
    for en, ru in rule.example_ok:
        assert rule.id not in qa.check_unit(en, ru, ruleset=only(rule.id)), \
            f"{rule.id}: пример молчания сработал — {en!r} / {ru!r}"


# --- the integrity of the set itself ------------------------------------


def test_ids_are_unique() -> None:
    assert len(qa_rules.BY_ID) == len(RULES)


def test_every_rule_has_a_known_category_and_severity() -> None:
    for rule in RULES:
        assert rule.category in qa_rules.CATEGORIES, rule.id
        assert rule.severity in qa_rules.SEVERITIES, rule.id


def test_every_rule_has_a_title_and_message() -> None:
    for rule in RULES:
        assert rule.title and rule.message, rule.id


def test_every_rule_is_implemented() -> None:
    """A rule without a check would keep quiet always — worse than its absence."""
    special = set(qa_rules.PROJECT_WIDE) | {qa_rules.EMPTY}
    for rule in RULES:
        if rule.id in special:
            continue
        assert rule.id in qa_rules.CHECKS, f"{rule.id}: нет реализации"


def test_no_orphan_checks() -> None:
    assert set(qa_rules.CHECKS) <= set(qa_rules.BY_ID)


def test_params_are_json_friendly() -> None:
    """The settings will travel into a file — so only simple types."""
    import json

    for rule in RULES:
        json.dumps(rule.params, ensure_ascii=False)

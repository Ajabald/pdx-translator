"""A change of the defaults is obliged only to quiet hits down.

Two parameters were moved to the position «compare with the original»:
`edge_space.compare_with_source` and `unbalanced_quotes.only_if_source_balanced`.
The reason is a measurement on the live agoot translation: 93% and 74% of the hits
fell on a space and a quote standing in the original itself.

The danger of such an edit is exactly one: a new default may not only remove what
is superfluous but also add a hit where there was none — and the translator gets a
stream of remarks for nothing. That is why the check is not «there is less of it»
but a strict one: the set of codes under the new defaults is a subset of the
former one, on every pair of the corpus.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from pdxloc.core import qa, qa_rules

# The former values — what the rules lived with before the change
OLD_DEFAULTS = {
    "edge_space": {"compare_with_source": False},
    "unbalanced_quotes": {"only_if_source_balanced": False},
}

# The pairs these rules are able to fire on at all: edge spaces, quotes and
# brackets in every combination of «in the original / not in the original».
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
    """Otherwise the edit would be pointless and the test above a tautology."""
    removed = set()
    for en, ru in CORPUS:
        removed |= (set(qa.check_unit(en, ru, ruleset=old_ruleset()))
                    - set(qa.check_unit(en, ru)))
    assert removed == set(OLD_DEFAULTS)


def test_every_rule_agrees_with_its_own_examples() -> None:
    """An example of an error is obliged to fire, an example of the norm to keep quiet.

    A default is changed for the sake of silence, and it is easy to arrive at a rule
    that keeps quiet always. The examples inside the rules are its own self-check.
    """
    rules = qa_rules.default_ruleset()
    for rule in rules:
        single = rules.restricted_to({rule.id})
        for en, ru in rule.example_bad:
            assert single.check(en, ru) == [rule.id], f"{rule.id}: {en!r} → {ru!r}"
        for en, ru in rule.example_ok:
            assert single.check(en, ru) == [], f"{rule.id}: {en!r} → {ru!r}"


def test_severity_of_a_rule_can_be_lowered_to_a_signal() -> None:
    """`info` was set up for the sake of `inconsistent`: that is a reason to check, not an error."""
    rules = qa_rules.default_ruleset()
    quiet = rules.with_rule(
        replace(rules.get("inconsistent"), severity=qa_rules.INFO))
    assert quiet.severity("inconsistent") == qa_rules.INFO
    assert qa_rules.SEVERITY_RANK[qa_rules.INFO] > qa_rules.SEVERITY_RANK[
        qa_rules.WARNING]

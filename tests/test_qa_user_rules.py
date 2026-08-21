"""Check rules of one's own: six declarative kinds and how they are stored.

The main property the kinds were made this way for: **somebody else's rule is
data, not code**. It arrives from a project file, from the global setting and
from an exchange file, and any of the three places may turn out to be written by
another version of the application or simply spoilt. Not one such case has the
right either to bring down a pass over a hundred thousand rows or to substitute a
built-in check.
"""
from __future__ import annotations

import json

import pytest

from pdxloc.core import qa_rules


def rule(kind: str, **params):
    return qa_rules.make_user_rule("own", kind, title="Своё", params=params)


def check(rule_obj, en: str, ru: str) -> list[str]:
    return qa_rules.RuleSet([rule_obj]).check(en, ru)


# --- the six kinds -------------------------------------------------------


CASES = [
    # (kind, parameters, original, translation-with-an-error, translation-without-one)
    # a multiset is for what is obliged to stay word for word; a count is for what
    # gets translated and can only match by number
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
    """A kind without a label cannot be chosen, a kind without a check keeps quiet always."""
    for kind_id in qa_rules.KIND_ORDER:
        kind = qa_rules.KINDS[kind_id]
        assert kind.title and kind.hint
        assert callable(kind.check)


def test_count_direction_ignores_extra_matches() -> None:
    own = rule("token_count", pattern=r"\d+", direction="fewer")
    assert check(own, "1 2", "1") == ["own"]
    assert check(own, "1", "1 2") == []


def test_pair_regex_answer_is_plain_text_by_default() -> None:
    """`$\\1$` in the role of an expression would mean «end of row» and would find nothing."""
    own = rule("pair_regex", source=r"\$(\w+)\$", target=r"$\1$")
    assert check(own, "Cost: $GOLD$", "Цена: $GOLD$") == []


def test_pair_regex_survives_a_template_without_a_group() -> None:
    own = rule("pair_regex", source=r"\$\w+\$", target=r"$\3$")
    assert check(own, "Cost: $GOLD$", "Цена") == []


def test_balance_counts_identical_halves_by_parity() -> None:
    """For «"» the equality of the counters holds always and means nothing."""
    own = rule("balance", pairs=['""'])
    assert check(own, "plain", 'Он сказал "да') == ["own"]
    assert check(own, "plain", 'Он сказал "да"') == []


def test_forbidden_chars_can_forgive_the_original() -> None:
    own = rule("forbidden_chars", chars="…", ignore_if_in_source=True)
    assert check(own, "Wait…", "Подожди…") == []
    assert check(own, "Wait...", "Подожди…") == ["own"]


def test_groups_in_the_pattern_do_not_change_what_is_counted() -> None:
    """`findall` would hand back the groups instead of the matches, and the rule would change its meaning."""
    with_group = rule("token_multiset", pattern=r"%(\w+)%")
    without = rule("token_multiset", pattern=r"%\w+%")
    en, ru = "%NAME%", "%ИМЯ%"
    assert check(with_group, en, ru) == check(without, en, ru) == ["own"]


# --- a broken expression -------------------------------------------------


@pytest.mark.parametrize("kind,params", [
    ("token_multiset", {"pattern": "([a-z"}),
    ("token_count", {"pattern": "([a-z"}),
    ("target_regex", {"pattern": "([a-z"}),
    ("pair_regex", {"source": "([a-z"}),
])
def test_broken_expression_silences_only_its_own_rule(kind, params) -> None:
    """Falling over mid-pass through a project because of somebody's typo will not do."""
    own = rule(kind, **params)
    rules = qa_rules.with_user_rules(qa_rules.default_ruleset(), [own])
    codes = rules.check("Cost: $V$", "Цена")
    assert "own" not in codes
    assert "dollar_mismatch" in codes        # the rest work as they worked


def test_empty_expression_is_not_an_error_yet() -> None:
    """The rule has only just been set up — it must not complain about every row."""
    assert check(rule("token_multiset"), "a", "b") == []
    assert check(rule("target_regex"), "a", "b") == []


def test_a_broken_parameter_silences_its_rule_not_the_whole_pass() -> None:
    """A typo in a number quiets its own rule, not a pass over a hundred thousand rows.

    `qa_rules.json` is carried between machines, `.pdxqa` files are sent to one
    another — both files are edited by hand, that is what they are for. A value of
    the wrong type reaches `int()` already inside the check; that used to bring
    the whole check down, together with the column of remarks and the F6 report.
    """
    broken = qa_rules.apply_delta(
        qa_rules.default_ruleset(),
        {"glued_markup": {"params": {"min_word_len": "три"}}})

    codes = broken.check("Hi $NAME$", "Привет")

    assert "dollar_mismatch" in codes       # the neighbouring rules work
    assert "glued_markup" not in codes      # the broken one keeps quiet


def test_regex_error_tells_what_is_wrong() -> None:
    assert qa_rules.regex_error("([a-z")
    assert qa_rules.regex_error(r"\d+") == ""
    assert qa_rules.regex_error("") == ""


def test_a_pattern_that_can_hang_the_check_is_flagged() -> None:
    """A repeat inside a repeated group is an exponential search.

    There is nothing to interrupt `re` with: it has no timeout, and signals do not
    work on Windows. So the only protection is to say so in the rules window,
    before the check goes over a hundred thousand rows. Rules also travel between
    people in a `.pdxqa` file, so the warning is needed for a foreign rule too.
    """
    assert qa_rules.regex_warning(r"(\w+)+$")
    assert qa_rules.regex_warning(r"(a*)*")
    assert qa_rules.regex_warning(r"(\d+\s?)+")

    # ordinary expressions keep quiet
    assert qa_rules.regex_warning(r"\d+") == ""
    assert qa_rules.regex_warning(r"(?:\w+)\s*") == ""
    assert qa_rules.regex_warning(r"\[[^\]]+\]") == ""
    assert qa_rules.regex_warning("") == ""
    # a broken expression is the business of regex_error, here we keep quiet
    assert qa_rules.regex_warning("([a-z") == ""


# --- reading somebody else's record --------------------------------------


def test_user_rule_cannot_shadow_a_builtin_check() -> None:
    """Otherwise somebody else's file would substitute its own expression for the bracket check."""
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
    # an unknown category would take the rule out of the window tree entirely
    assert loaded.category in qa_rules.CATEGORIES


def test_unknown_severity_falls_back_to_warning() -> None:
    loaded = qa_rules.load_user_rule(
        {"id": "x", "kind": "forbidden_chars", "title": "x", "severity": "кошмар"})
    assert loaded.severity == qa_rules.WARNING


# --- storage in the overlay ----------------------------------------------


def test_user_rule_is_stored_whole_and_restored() -> None:
    own = rule("forbidden_chars", chars="…")
    rules = qa_rules.with_user_rules(qa_rules.default_ruleset(), [own])
    overlay = json.loads(json.dumps(
        qa_rules.make_overlay(qa_rules.CUSTOM, rules), ensure_ascii=False))

    restored = qa_rules.resolve(overlay)
    assert restored.get("own").params["chars"] == "…"
    assert restored.check("Wait...", "Подожди…") == ["own"]


def test_project_layer_does_not_copy_a_global_user_rule() -> None:
    """The rule is set up for all the projects — that is where it is to live."""
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
    """As with the built-in language rules: it shows in the window, it is switched on by hand."""
    own = qa_rules.make_user_rule("own", "forbidden_chars", title="Своё",
                                  locale="ru", params={"chars": "…"})
    overlay = {"custom": [qa_rules.dump_user_rule(own)]}
    rules = qa_rules.resolve(overlay, locale="fr")
    assert rules.get("own") is not None
    assert not rules.get("own").enabled
    assert qa_rules.resolve(overlay, locale="ru").get("own").enabled

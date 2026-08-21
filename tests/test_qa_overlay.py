"""The overlays of a rule set: the delta, the two layers, the presets.

The main property the overlay was made a delta and not a full dump for: an update
of the application is obliged to reach the user. A set saved whole would freeze
the rules at the version it was written in — new rules would not appear, and
mended defaults would not apply.
"""
from __future__ import annotations

import json

import pytest

from pdxloc import project as project_module
from pdxloc.core import inflections, qa, qa_rules


# --- merging the layers -------------------------------------------------


def test_empty_overlay_changes_nothing() -> None:
    resolved = qa_rules.resolve({}, None)
    default = qa_rules.default_ruleset()
    assert [r for r in resolved] == [r for r in default]


def test_delta_touches_only_named_rules() -> None:
    rules = qa_rules.resolve({"rules": {"len_ratio": {"enabled": True}}})
    assert rules.get("len_ratio").enabled
    assert rules.get("edge_space") == qa_rules.BY_ID["edge_space"]


def test_project_layer_wins_over_global() -> None:
    rules = qa_rules.resolve(
        {"rules": {"same_as_en": {"severity": qa_rules.INFO}}},
        {"rules": {"same_as_en": {"severity": qa_rules.ERROR}}},
    )
    assert rules.severity("same_as_en") == qa_rules.ERROR


def test_project_layer_keeps_untouched_global_edits() -> None:
    """The project edits its own, while the global settings stay in force."""
    rules = qa_rules.resolve(
        {"rules": {"len_ratio": {"enabled": True}}},
        {"rules": {"same_as_en": {"enabled": False}}},
    )
    assert rules.get("len_ratio").enabled
    assert not rules.get("same_as_en").enabled


def test_unknown_rule_in_overlay_is_ignored() -> None:
    """The overlay was written by another version — falling over because of that will not do."""
    rules = qa_rules.resolve({"rules": {"такого_правила_нет": {"enabled": False}}})
    assert len(rules) == len(qa_rules.BUILTIN_RULES)


def test_unknown_param_in_overlay_is_ignored() -> None:
    rules = qa_rules.resolve(
        {"rules": {"edge_space": {"params": {"такого_нет": 1}}}})
    assert "такого_нет" not in rules.get("edge_space").params


def test_unknown_severity_in_overlay_is_ignored() -> None:
    rules = qa_rules.resolve({"rules": {"same_as_en": {"severity": "кошмар"}}})
    assert rules.severity("same_as_en") == qa_rules.BY_ID["same_as_en"].severity


# --- the presets --------------------------------------------------------


@pytest.mark.parametrize("name", qa_rules.PRESET_ORDER)
def test_every_preset_is_applicable_and_described(name: str) -> None:
    rules = qa_rules.resolve({"preset": name})
    assert len(rules) == len(qa_rules.BUILTIN_RULES)
    # The label of a game set arrives from the registry of games and not from a
    # table of strings: «Crusader Kings III» is the same in every interface language.
    assert qa_rules.preset_label(name)
    assert qa_rules.PRESET_NOTES[name]


def test_the_recommended_preset_is_the_one_named_after_the_game() -> None:
    """A set is called by the game, so there is nothing to pick it by — it is the game.

    Before 0.1.2 there was a table of «game plus language» pairs here, because the
    language was written into the set itself: for CK3 it was called `ck3_ru`. The
    language moved off into a layer of its own, and the table collapsed.
    """
    assert qa_rules.recommended("hoi4") == "hoi4"
    assert qa_rules.recommended("ck3") == "ck3"
    # a game without a set of its own and a closed project: silence is honester than invention
    assert qa_rules.recommended("vic3") is None
    assert qa_rules.recommended("") is None


@pytest.mark.parametrize("game", ["hoi4", "vic3", ""])
def test_display_order_is_a_permutation_of_the_registry(game) -> None:
    """The shop window rearranges the sets, it does not lose or double them."""
    order = qa_rules.display_order(game)
    assert sorted(order) == sorted(qa_rules.PRESET_ORDER)
    best = qa_rules.recommended(game)
    if best is not None:
        assert order[0] == best
    else:
        assert order == qa_rules.PRESET_ORDER


def test_old_preset_names_still_resolve() -> None:
    """The names from before 0.1.2 lie in qa_rules.json, in projects and in exported .pdxqa.

    Forget about them — and a human's setting would silently turn into «Custom».
    """
    for old, now in qa_rules.PRESET_ALIASES.items():
        assert qa_rules.preset_of({"preset": old}) == now, old
        assert now in qa_rules.PRESETS


def test_the_language_layer_attaches_by_the_target_language() -> None:
    """The language layer is not chosen — it comes with the target language of the project."""
    fr = qa_rules.resolve({"preset": "hoi4"}, locale="fr")
    ru = qa_rules.resolve({"preset": "hoi4"}, locale="ru")
    none = qa_rules.resolve({"preset": "hoi4"})

    def tails(rules):
        return rules.get("brackets_mismatch").params["ignore_extra_tails"]

    assert len(tails(fr)) > 100        # the French HOI4 declines more actively than any
    assert len(tails(ru)) == len(inflections.HOI4_RU_CALLS)
    assert not tails(none)             # there is no language — and nothing to invent with
    assert set(tails(fr)) != set(tails(ru))


def test_preset_deltas_name_only_existing_rules_and_params() -> None:
    """Otherwise a typo in a preset would silently do nothing."""
    for name, delta in qa_rules.PRESETS.items():
        for rule_id, changes in delta.items():
            rule = qa_rules.BY_ID.get(rule_id)
            assert rule is not None, f"{name}: нет правила {rule_id}"
            for param in changes.get("params", {}):
                assert param in rule.params, f"{name}/{rule_id}: нет параметра {param}"


def test_recommended_preset_is_quieter_than_builtin_defaults() -> None:
    """That is what the preset was set up for: a wrapper for declension is a device, not an error."""
    en = "Dusk King [GetTitle]"
    ru = "[Select_CString(CHARACTER.IsFemale, 'Королева', 'Король')] заката"
    assert "brackets_mismatch" in qa.check_unit(en, ru)
    ck3_ru = qa_rules.resolve({"preset": "ck3_ru"})
    assert "brackets_mismatch" not in qa.check_unit(en, ru, ruleset=ck3_ru)


def test_quiet_preset_keeps_only_what_breaks_the_game() -> None:
    quiet = qa_rules.resolve({"preset": "quiet"})
    assert "dollar_mismatch" in quiet.active_ids()
    assert "edge_space" not in quiet.active_ids()
    # but even in it a lost variable stays an error
    assert qa.check_unit("Cost: $V$", "Цена", ruleset=quiet) == ["dollar_mismatch"]


def test_strict_preset_turns_everything_on() -> None:
    strict = qa_rules.resolve({"preset": "strict"})
    assert strict.active_ids() == {r.id for r in qa_rules.BUILTIN_RULES}


# --- writing the delta --------------------------------------------------


def test_overlay_records_only_the_difference() -> None:
    rules = qa_rules.default_ruleset()
    edited = rules.with_rule(
        rules.get("len_ratio").with_params(min_ratio=0.3))
    overlay = qa_rules.make_overlay(qa_rules.CUSTOM, edited)
    assert overlay["rules"] == {"len_ratio": {"params": {"min_ratio": 0.3}}}


def test_overlay_over_a_preset_does_not_copy_the_preset() -> None:
    """Otherwise the set would freeze: an edit of the preset in a new version the project will not see."""
    rules = qa_rules.resolve({"preset": "ck3_ru"})
    overlay = qa_rules.make_overlay("ck3_ru", rules)
    assert overlay["rules"] == {}
    # the former name is understood, but the present one is written: files must not breed the old one
    assert overlay["preset"] == "ck3"


def test_project_overlay_does_not_copy_global_edits() -> None:
    glob = {"rules": {"len_ratio": {"enabled": True}}}
    rules = qa_rules.resolve(glob)
    overlay = qa_rules.make_overlay(qa_rules.CUSTOM, rules, under=glob)
    assert overlay["rules"] == {}


def test_overlay_round_trips_through_json_and_resolve() -> None:
    # the way a user does it: chose a set, then edits a rule
    rules = qa_rules.resolve({"preset": "ck3_ru"})
    edited = rules.with_rule(qa_rules.replace(
        rules.get("same_as_en"), enabled=False, severity=qa_rules.INFO))
    overlay = json.loads(json.dumps(
        qa_rules.make_overlay("ck3_ru", edited), ensure_ascii=False))
    assert set(overlay["rules"]) == {"same_as_en"}      # only the edit, not the whole set

    restored = qa_rules.resolve(overlay)
    assert not restored.get("same_as_en").enabled
    assert restored.severity("same_as_en") == qa_rules.INFO
    # and the preset arrived together with the edit
    assert restored.get("inconsistent").severity == qa_rules.INFO


def test_empty_overlay_is_recognised_and_not_stored() -> None:
    assert qa_rules.is_empty_overlay(None)
    assert qa_rules.is_empty_overlay({"version": 1, "preset": None, "rules": {}})
    assert not qa_rules.is_empty_overlay({"preset": "quiet"})


# --- the layer inside the project file ----------------------------------


@pytest.fixture
def conn(tmp_path):
    c = project_module.create_project(
        tmp_path / "p.pdxproj", name="P",
        src_root=tmp_path / "en", tgt_root=tmp_path / "ru")
    yield c
    c.close()


def test_project_overlay_survives_reopen(conn, tmp_path) -> None:
    overlay = qa_rules.make_overlay("quiet", qa_rules.resolve({"preset": "quiet"}))
    project_module.set_qa_overlay(conn, overlay)
    conn.close()

    again = project_module.open_project(tmp_path / "p.pdxproj", [])
    try:
        assert project_module.get_qa_overlay(again)["preset"] == "quiet"
    finally:
        again.close()


def test_empty_project_overlay_is_erased(conn) -> None:
    project_module.set_qa_overlay(conn, {"preset": "quiet", "rules": {}})
    project_module.set_qa_overlay(conn, {"preset": None, "rules": {}})
    assert project_module.get_qa_overlay(conn) == {}


def test_broken_project_overlay_does_not_crash(conn) -> None:
    conn.execute("INSERT INTO project_meta (key, value) VALUES ('qa_overlay', ?)",
                 ("{не json",))
    conn.commit()
    assert project_module.get_qa_overlay(conn) == {}

"""The `.pdxqa` file for exchanging a check setup.

Two properties it was set up for:

* **self-sufficiency** — the receiver gets exactly the set the author had, without
  the author's global layer, which the receiver knows nothing about;
* **defensive reading** — somebody else's file is data. What is unknown is
  skipped, but the human is told how much was skipped: inside an overlay a silent
  skip is justified by a difference of versions, while here the user expects that
  everything arrived.
"""
from __future__ import annotations

import json

import pytest

from pdxloc.core import qa_exchange, qa_rules


def user_rule(rule_id: str = "no_ellipsis", chars: str = "…"):
    return qa_rules.make_user_rule(rule_id, "forbidden_chars",
                                   title="Троеточие одним символом",
                                   params={"chars": chars})


# --- the round: written, read -------------------------------------------


def test_round_trip_through_a_file(tmp_path) -> None:
    rules = qa_rules.with_user_rules(
        qa_rules.resolve({"preset": "ck3_ru"}), [user_rule()])
    rules = rules.with_rule(qa_rules.replace(
        rules.get("same_as_en"), enabled=False))

    path = qa_exchange.write(tmp_path / "team", "ck3_ru", rules)
    assert path.suffix == qa_exchange.SUFFIX      # the extension is added by itself

    bundle = qa_exchange.read(path)
    restored = bundle.ruleset()
    # the name of the set arrives as the present one: the file was written before
    # 0.1.2, when the game and the language lived together, and `ck3_ru` is today's `ck3`
    assert bundle.preset == "ck3"
    assert bundle.skipped == ()
    assert [r.id for r in restored] == [r.id for r in rules]
    assert not restored.get("same_as_en").enabled
    assert restored.get("no_ellipsis").params["chars"] == "…"
    # the preset arrived as a name and not as a copy: there are no edits of its rules in the file
    assert "brackets_mismatch" not in bundle.changed


def test_the_file_does_not_depend_on_the_layer_below(tmp_path) -> None:
    """The receiver does not have this layer, and the set would come out different."""
    glob = {"rules": {"len_ratio": {"enabled": True}}}
    rules = qa_rules.resolve(glob)
    path = qa_exchange.write(tmp_path / "s.pdxqa", qa_rules.CUSTOM, rules)

    restored = qa_exchange.read(path).ruleset()
    assert restored.get("len_ratio").enabled


def test_export_notes_the_application_version(tmp_path) -> None:
    data = qa_exchange.dump(qa_rules.CUSTOM, qa_rules.default_ruleset(),
                            app_version="9.9.9")
    assert data["app"] == "9.9.9" and data["format"] == qa_exchange.FORMAT


# --- a foreign and a broken file ----------------------------------------


def test_a_foreign_file_is_refused(tmp_path) -> None:
    path = tmp_path / "x.pdxqa"
    path.write_text(json.dumps({"format": "xbench"}), encoding="utf-8")
    with pytest.raises(qa_exchange.ExchangeError):
        qa_exchange.read(path)


def test_broken_json_is_refused(tmp_path) -> None:
    path = tmp_path / "x.pdxqa"
    path.write_text("{не json", encoding="utf-8")
    with pytest.raises(qa_exchange.ExchangeError):
        qa_exchange.read(path)


def test_a_missing_file_is_refused(tmp_path) -> None:
    with pytest.raises(qa_exchange.ExchangeError):
        qa_exchange.read(tmp_path / "нет такого.pdxqa")


def test_a_newer_version_is_refused() -> None:
    """Reading by halves is worse than saying «a fresh version is needed»."""
    with pytest.raises(qa_exchange.ExchangeError):
        qa_exchange.parse({"format": qa_exchange.FORMAT,
                           "version": qa_exchange.VERSION + 1})


@pytest.mark.parametrize("version", ["вчера", [1], {"a": 1}])
def test_a_broken_version_is_refused_as_a_file_error(version) -> None:
    """The version number is somebody else's data too, and the window must not fall over on it."""
    with pytest.raises(qa_exchange.ExchangeError):
        qa_exchange.parse({"format": qa_exchange.FORMAT, "version": version})


def test_unknown_rules_are_skipped_and_counted() -> None:
    bundle = qa_exchange.parse({
        "format": qa_exchange.FORMAT, "version": 1, "preset": "ck3_ru",
        "rules": {"edge_space": {"enabled": False}, "правила_нет": {"enabled": False}},
        "custom": [
            qa_rules.dump_user_rule(user_rule()),
            {"id": "future", "kind": "вида_нет", "title": "x"},
            {"id": "brackets_mismatch", "kind": "target_regex", "title": "подмена"},
        ],
    })
    assert bundle.changed == ("edge_space",)
    assert bundle.added == ("no_ellipsis",)
    assert set(bundle.skipped) == {"правила_нет", "future", "brackets_mismatch"}
    # and no substitution of a built-in check happened
    assert bundle.ruleset().get("brackets_mismatch").kind == qa_rules.BUILTIN


def test_an_unknown_preset_falls_back_to_own_and_is_reported() -> None:
    bundle = qa_exchange.parse({"format": qa_exchange.FORMAT, "version": 1,
                                "preset": "супер_строгий"})
    assert bundle.preset == qa_rules.CUSTOM
    assert bundle.skipped == ("супер_строгий",)


def test_the_locale_of_the_receiving_project_still_applies() -> None:
    """A file from a Russian project must not switch the Russian rules on for a Frenchman."""
    data = qa_exchange.dump("strict", qa_rules.resolve({"preset": "strict"}))
    rules = qa_exchange.parse(data).ruleset(locale="fr")
    assert not rules.get("glued_markup").enabled


def test_the_language_of_the_sender_does_not_travel_with_the_file() -> None:
    """For a translator into French the Russian rules keep quiet — to the receiver that is no setting."""
    french = qa_rules.resolve({"preset": "strict"}, locale="fr")
    data = qa_exchange.dump("strict", french, locale="fr")
    assert "glued_markup" not in data["rules"]
    assert qa_exchange.parse(data).ruleset(locale="ru").get("glued_markup").enabled

"""The check «a space is missing before the substitution».

The reason: in a live project 18 rows of the kind «дома[GetPlayer.GetDynasty…]»
turned up — in the game that sticks together into «домаСтарк». Not one of the
former checks saw such a thing: `edge_space` looks at the edges of a row,
`double_space` at extra spaces and not at a missing one.

The main difficulty of the rule is that a join happens to be DELIBERATE, and there
are three such devices. Each is covered by a test of its own — should the rule
start catching them, the «!» column will drown in noise, as already happened with
the check of tag balance.
"""
from __future__ import annotations

import pytest

from pdxloc.core.qa import CODES, check_unit

GLUED = "glued_markup"


def codes(en: str, ru: str) -> list[str]:
    return check_unit(en, ru)


# --- what the rule was set up for ---------------------------------------


def test_lost_space_before_name_substitution() -> None:
    assert GLUED in codes(
        "The wealth of House [GetPlayer.GetDynasty.GetNameNoTooltip] grows.",
        "Богатства дома[GetPlayer.GetDynasty.GetNameNoTooltip] растут.")


def test_lost_space_before_trait_lookup() -> None:
    assert GLUED in codes(
        "Ashfords tend to be [GetTrait('loyal').GetName( GetNullCharacter )].",
        "У Эшфордов часто проявляется черта[GetTrait('loyal').GetName( GetNullCharacter )].")


def test_lost_space_before_concept() -> None:
    assert GLUED in codes(
        "Opens a [decision|E]",
        "Открывает[Concept('decision', 'решение')|E]")


def test_severity_is_warning_not_error() -> None:
    """The text reads awkwardly, but the game does not break — as with the neighbouring rules."""
    assert CODES[GLUED][0] == "warning"


# --- deliberate joins: these must not be caught -------------------------


def test_gender_ending_is_not_an_error() -> None:
    """Select_CString returns an ending: «даровал» + «а» = «даровала»."""
    assert GLUED not in codes(
        "[X.GetSheHe|U] granted the boon.",
        "[X.GetSheHe|U] даровал[Select_CString(X.IsFemale, 'а', '')] дар.")


def test_custom_ending_function_is_not_an_error() -> None:
    """Translators set up functions with the _END suffix specially for endings."""
    assert GLUED not in codes(
        "a white [ROOT.Char.Custom('GetAnimalType')]",
        "бел[ROOT.Char.Custom('GetAnimalType_RU_Acc_END')]")


def test_pronoun_stem_is_not_an_error() -> None:
    """«к н» + «ему/ей» is a join of a pronoun, one letter before the insert."""
    assert GLUED not in codes(
        "closer to [target.GetHerHim]",
        "ближе к н[target.Custom('GetDragonHerHis')]")


def test_glue_inherited_from_the_original_is_not_an_error() -> None:
    """In the original the icon stands right against the word — the translation may do the same."""
    assert GLUED not in codes(
        "[command_modifier_i|E]Minimum roll",
        "[command_modifier_i|E]Худший бросок")


def test_escape_sequence_is_not_a_letter() -> None:
    """«\\n[X]» is a line break, not the letter n glued to an insert."""
    assert GLUED not in codes(
        "Line one.\\n[SCOPE.GetName] speaks.",
        "Строка одна.\\n[SCOPE.GetName] говорит.")


def test_space_present_is_clean() -> None:
    assert GLUED not in codes(
        "House [GetPlayer.GetDynasty.GetNameNoTooltip]",
        "дома [GetPlayer.GetDynasty.GetNameNoTooltip]")


# --- the behaviour on a live project ------------------------------------


@pytest.mark.realdata
def test_rule_stays_quiet_on_a_clean_project(tmp_path) -> None:
    """The rule must not be noisy: the share of hits is a fraction of a percent.

    Measured on agoot (136,113 rows): 14 hits, 3 of them false. Here we pin down
    only the order of magnitude, so as to catch a regression of the rule.
    """
    import sqlite3
    from pathlib import Path

    # the projects live in the pen of their game (see core/games.py)
    project = Path("Projects/CK3/agoot.pdxproj")
    if not project.is_file():
        pytest.skip("нет живого проекта agoot")
    conn = sqlite3.connect(f"file:{project}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT en_text, ru_text FROM units WHERE is_deleted=0 "
        "AND en_text IS NOT NULL AND ru_text IS NOT NULL AND status != 'ignored'"
    ).fetchall()
    hits = sum(1 for r in rows if GLUED in check_unit(r["en_text"], r["ru_text"]))
    conn.close()
    assert hits / len(rows) < 0.005, f"правило зашумело: {hits} из {len(rows)}"

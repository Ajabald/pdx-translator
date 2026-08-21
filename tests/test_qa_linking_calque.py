"""The check «a substitution after a linking verb».

The reason: CK3 names the traits in the Russian localisation with nouns —
`trait_loyal` = «Верность», `trait_brave` = «Отвага». The English «Beesburys tend
to be [GetTrait('loyal')…]» is translated literally as «Бисбери склонны быть
[GetTrait…]», and in the game that unfolds into «склонны быть Верность». In a
live project 72 such calques were found.

It is cured not by scripted grammar but by a turn of phrase with an apposition —
«склонны проявлять черту: Верность». That is what the vanilla localisation itself
does: «получает свойство „[GetTrait('heir_in_training').GetName(…)]“».

The danger of the rule is catching a link in the position of the SUBJECT, where
the nominative case is right. Such turns are covered by tests of their own: the
measurement showed that without them the rule gives 21 false hits over 136,000
rows, and with them none.
"""
from __future__ import annotations

from pdxloc.core.qa import CODES, check_unit

CALQUE = "linking_calque"

TRAIT = "[GetTrait('loyal').GetName( GetNullCharacter )]"


def codes(en: str, ru: str) -> list[str]:
    return check_unit(en, ru)


# --- what the rule was set up for ---------------------------------------


def test_tend_to_be_calque() -> None:
    assert CALQUE in codes(
        f"Beesburys tend to be {TRAIT}.",
        f"Бисбери склонны быть {TRAIT}.")


def test_usually_are_calque() -> None:
    assert CALQUE in codes(
        f"Plumms tend to be {TRAIT}.",
        f"Пламмы обычно бывают {TRAIT}.")


def test_are_born_calque() -> None:
    assert CALQUE in codes(
        f"Members of the Vance dynasty are frequently born {TRAIT}.",
        f"Отпрыски дома Вэнс часто рождаются {TRAIT}.")


def test_are_considered_calque() -> None:
    assert CALQUE in codes(
        f"Manderlys are considered {TRAIT}.",
        f"Мандерли считаются {TRAIT}.")


def test_may_be_calque() -> None:
    assert CALQUE in codes(
        f"Oakhearts may be {TRAIT}.",
        f"Окхарты могут быть {TRAIT}.")


def test_severity_is_warning() -> None:
    """The game does not break — only the readability suffers."""
    assert CODES[CALQUE][0] == "warning"


# --- the position of the subject: the nominative is right, catching is not allowed ---


def test_subject_position_with_yavlyaetsya_is_fine() -> None:
    """«целью которых является [Имя]» — the substitution here is the subject."""
    assert CALQUE not in codes(
        "the scheme targeting [TARGET_CHARACTER.GetShortUIName]",
        "происки, целью которых является [TARGET_CHARACTER.GetShortUIName]")


def test_negated_cannot_be_is_fine() -> None:
    """«целью не может быть [X]» — the subject as well."""
    assert CALQUE not in codes(
        "The target cannot be [GetTrait('witch').GetName( CHARACTER.Self )]",
        "Целью шантажа не может быть [GetTrait('witch').GetName( CHARACTER.Self )]")


def test_dolzhen_byt_is_fine() -> None:
    assert CALQUE not in codes(
        "You must own [GetDomicileBuilding('x').GetName]",
        "У вас должен быть [GetDomicileBuilding('x').GetName]")


def test_ceases_to_be_is_fine() -> None:
    assert CALQUE not in codes(
        "[X.GetShortUIName|U] is no longer [CHARACTER.GetHerHis] ward",
        "[X.GetShortUIName|U] перестает быть [CHARACTER.GetHerHis] воспитанником")


# --- the right turn of phrase must not be caught ------------------------


def test_apposition_after_colon_is_clean() -> None:
    """The very device the calques get rewritten with."""
    assert CALQUE not in codes(
        f"Beesburys tend to be {TRAIT}.",
        f"Бисбери склонны проявлять черту: {TRAIT}.")


def test_born_with_trait_is_clean() -> None:
    assert CALQUE not in codes(
        f"Members of the Vance dynasty are frequently born {TRAIT}.",
        f"Отпрыски дома Вэнс часто рождаются с чертой: {TRAIT}.")


def test_instrumental_wrapper_is_clean() -> None:
    assert CALQUE not in codes(
        f"Balls tend to be {TRAIT}.",
        f"Боллы, как правило, обладают чертой {TRAIT}.")


def test_english_original_is_never_flagged() -> None:
    """The rule looks only at the translation: in English the link is impeccable."""
    assert CALQUE not in codes(
        f"Beesburys tend to be {TRAIT}.",
        f"У Бисбери часто проявляется черта: {TRAIT}.")

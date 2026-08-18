"""Проверка «подстановка после глагола-связки».

Повод: CK3 называет черты в русской локализации существительными —
`trait_loyal` = «Верность», `trait_brave` = «Отвага». Английское «Beesburys
tend to be [GetTrait('loyal')…]» переводится буквально как «Бисбери склонны
быть [GetTrait…]», и в игре это разворачивается в «склонны быть Верность».
В живом проекте таких калек нашлось 72.

Лечится не скриптовой грамматикой, а оборотом с приложением — «склонны
проявлять черту: Верность». Так делает и сама ванильная локализация:
«получает свойство „[GetTrait('heir_in_training').GetName(…)]“».

Опасность правила — зацепить связку в позиции ПОДЛЕЖАЩЕГО, где именительный
падеж правилен. Такие обороты закрыты отдельными тестами: замер показал, что
без них правило даёт 21 ложное срабатывание на 136 000 строк, с ними — ноль.
"""
from __future__ import annotations

from pdxloc.core.qa import CODES, check_unit

CALQUE = "linking_calque"

TRAIT = "[GetTrait('loyal').GetName( GetNullCharacter )]"


def codes(en: str, ru: str) -> list[str]:
    return check_unit(en, ru)


# --- то, ради чего правило заведено -------------------------------------


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
    """Игра не ломается — страдает только читаемость."""
    assert CODES[CALQUE][0] == "warning"


# --- позиция подлежащего: именительный правилен, ловить нельзя -----------


def test_subject_position_with_yavlyaetsya_is_fine() -> None:
    """«целью которых является [Имя]» — подстановка здесь подлежащее."""
    assert CALQUE not in codes(
        "the scheme targeting [TARGET_CHARACTER.GetShortUIName]",
        "происки, целью которых является [TARGET_CHARACTER.GetShortUIName]")


def test_negated_cannot_be_is_fine() -> None:
    """«целью не может быть [X]» — тоже подлежащее."""
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


# --- правильный оборот не должен ловиться -------------------------------


def test_apposition_after_colon_is_clean() -> None:
    """Тот приём, которым переписываются кальки."""
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
    """Правило смотрит только на перевод: по-английски связка безупречна."""
    assert CALQUE not in codes(
        f"Beesburys tend to be {TRAIT}.",
        f"У Бисбери часто проявляется черта: {TRAIT}.")

"""Проверка «пропущен пробел перед подстановкой».

Повод: в живом проекте нашлось 18 строк вида «дома[GetPlayer.GetDynasty…]» —
в игре это склеивается в «домаСтарк». Ни одна из прежних проверок такого не
видела: `edge_space` смотрит на края строки, `double_space` — на лишние
пробелы, а не на пропущенный.

Главная трудность правила в том, что склейка бывает НАМЕРЕННОЙ, и таких
приёмов три. Каждый закрыт отдельным тестом — если правило начнёт их ловить,
колонка «!» утонет в шуме, как это уже было с проверкой баланса тегов.
"""
from __future__ import annotations

import pytest

from pdxloc.core.qa import CODES, check_unit

GLUED = "glued_markup"


def codes(en: str, ru: str) -> list[str]:
    return check_unit(en, ru)


# --- то, ради чего правило заведено -------------------------------------


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
    """Текст читается криво, но игра не ломается — как и у соседних правил."""
    assert CODES[GLUED][0] == "warning"


# --- намеренные склейки: ловить нельзя ----------------------------------


def test_gender_ending_is_not_an_error() -> None:
    """Select_CString возвращает окончание: «даровал» + «а» = «даровала»."""
    assert GLUED not in codes(
        "[X.GetSheHe|U] granted the boon.",
        "[X.GetSheHe|U] даровал[Select_CString(X.IsFemale, 'а', '')] дар.")


def test_custom_ending_function_is_not_an_error() -> None:
    """Переводчики заводят функции с суффиксом _END специально под окончания."""
    assert GLUED not in codes(
        "a white [ROOT.Char.Custom('GetAnimalType')]",
        "бел[ROOT.Char.Custom('GetAnimalType_RU_Acc_END')]")


def test_pronoun_stem_is_not_an_error() -> None:
    """«к н» + «ему/ей» — склейка местоимения, перед вставкой одна буква."""
    assert GLUED not in codes(
        "closer to [target.GetHerHim]",
        "ближе к н[target.Custom('GetDragonHerHis')]")


def test_glue_inherited_from_the_original_is_not_an_error() -> None:
    """В оригинале иконка стоит вплотную к слову — перевод вправе так же."""
    assert GLUED not in codes(
        "[command_modifier_i|E]Minimum roll",
        "[command_modifier_i|E]Худший бросок")


def test_escape_sequence_is_not_a_letter() -> None:
    """«\\n[X]» — перенос строки, а не буква n, приклеенная к вставке."""
    assert GLUED not in codes(
        "Line one.\\n[SCOPE.GetName] speaks.",
        "Строка одна.\\n[SCOPE.GetName] говорит.")


def test_space_present_is_clean() -> None:
    assert GLUED not in codes(
        "House [GetPlayer.GetDynasty.GetNameNoTooltip]",
        "дома [GetPlayer.GetDynasty.GetNameNoTooltip]")


# --- поведение на живом проекте -----------------------------------------


@pytest.mark.realdata
def test_rule_stays_quiet_on_a_clean_project(tmp_path) -> None:
    """Правило не должно шуметь: доля срабатываний — доли процента.

    Замер на agoot (136 113 строк): 14 срабатываний, из них 3 ложных.
    Здесь фиксируем только порядок величины, чтобы поймать регрессию правила.
    """
    import sqlite3
    from pathlib import Path

    # проекты живут в загоне своей игры (см. core/games.py)
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

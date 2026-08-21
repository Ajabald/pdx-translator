"""Оверлеи набора правил: дельта, два слоя, пресеты.

Главное свойство, ради которого оверлей сделан дельтой, а не полным дампом:
обновление приложения обязано доезжать до пользователя. Сохранённый целиком
набор заморозил бы правила на версии, в которой его записали, — новые правила
не появились бы, а починенные дефолты не применились.
"""
from __future__ import annotations

import json

import pytest

from pdxloc import project as project_module
from pdxloc.core import inflections, qa, qa_rules


# --- слияние слоёв -------------------------------------------------------


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
    """Проект правит своё, глобальные настройки при этом остаются в силе."""
    rules = qa_rules.resolve(
        {"rules": {"len_ratio": {"enabled": True}}},
        {"rules": {"same_as_en": {"enabled": False}}},
    )
    assert rules.get("len_ratio").enabled
    assert not rules.get("same_as_en").enabled


def test_unknown_rule_in_overlay_is_ignored() -> None:
    """Оверлей писала другая версия — падать из-за этого нельзя."""
    rules = qa_rules.resolve({"rules": {"такого_правила_нет": {"enabled": False}}})
    assert len(rules) == len(qa_rules.BUILTIN_RULES)


def test_unknown_param_in_overlay_is_ignored() -> None:
    rules = qa_rules.resolve(
        {"rules": {"edge_space": {"params": {"такого_нет": 1}}}})
    assert "такого_нет" not in rules.get("edge_space").params


def test_unknown_severity_in_overlay_is_ignored() -> None:
    rules = qa_rules.resolve({"rules": {"same_as_en": {"severity": "кошмар"}}})
    assert rules.severity("same_as_en") == qa_rules.BY_ID["same_as_en"].severity


# --- пресеты -------------------------------------------------------------


@pytest.mark.parametrize("name", qa_rules.PRESET_ORDER)
def test_every_preset_is_applicable_and_described(name: str) -> None:
    rules = qa_rules.resolve({"preset": name})
    assert len(rules) == len(qa_rules.BUILTIN_RULES)
    # Подпись игрового набора приезжает из реестра игр, а не из таблицы строк:
    # «Crusader Kings III» одинаково на всех языках интерфейса.
    assert qa_rules.preset_label(name)
    assert qa_rules.PRESET_NOTES[name]


def test_the_recommended_preset_is_the_one_named_after_the_game() -> None:
    """Набор зовётся игрой, поэтому подбирать его нечем — он и есть игра.

    До 0.1.2 здесь была таблица пар «игра плюс язык», потому что язык был вписан
    в сам набор: у CK3 он звался `ck3_ru`. Язык уехал в свой слой, и таблица
    схлопнулась.
    """
    assert qa_rules.recommended("hoi4") == "hoi4"
    assert qa_rules.recommended("ck3") == "ck3"
    # игра без своего набора и закрытый проект: молчание честнее выдумки
    assert qa_rules.recommended("vic3") is None
    assert qa_rules.recommended("") is None


@pytest.mark.parametrize("game", ["hoi4", "vic3", ""])
def test_display_order_is_a_permutation_of_the_registry(game) -> None:
    """Витрина переставляет наборы, а не теряет и не двоит их."""
    order = qa_rules.display_order(game)
    assert sorted(order) == sorted(qa_rules.PRESET_ORDER)
    best = qa_rules.recommended(game)
    if best is not None:
        assert order[0] == best
    else:
        assert order == qa_rules.PRESET_ORDER


def test_old_preset_names_still_resolve() -> None:
    """Имена до 0.1.2 лежат в qa_rules.json, в проектах и в выгруженных .pdxqa.

    Забудь про них — и настройка человека молча превратилась бы в «Свой».
    """
    for old, now in qa_rules.PRESET_ALIASES.items():
        assert qa_rules.preset_of({"preset": old}) == now, old
        assert now in qa_rules.PRESETS


def test_the_language_layer_attaches_by_the_target_language() -> None:
    """Слой языка не выбирают — он приходит с языком перевода проекта."""
    fr = qa_rules.resolve({"preset": "hoi4"}, locale="fr")
    ru = qa_rules.resolve({"preset": "hoi4"}, locale="ru")
    none = qa_rules.resolve({"preset": "hoi4"})

    def tails(rules):
        return rules.get("brackets_mismatch").params["ignore_extra_tails"]

    assert len(tails(fr)) > 100        # французский HOI4 склоняет активнее всех
    assert len(tails(ru)) == len(inflections.HOI4_RU_CALLS)
    assert not tails(none)             # языка нет — и врать нечем
    assert set(tails(fr)) != set(tails(ru))


def test_preset_deltas_name_only_existing_rules_and_params() -> None:
    """Опечатка в пресете иначе молча ничего бы не делала."""
    for name, delta in qa_rules.PRESETS.items():
        for rule_id, changes in delta.items():
            rule = qa_rules.BY_ID.get(rule_id)
            assert rule is not None, f"{name}: нет правила {rule_id}"
            for param in changes.get("params", {}):
                assert param in rule.params, f"{name}/{rule_id}: нет параметра {param}"


def test_recommended_preset_is_quieter_than_builtin_defaults() -> None:
    """Ради этого пресет и заведён: обёртка ради склонения — приём, не ошибка."""
    en = "Dusk King [GetTitle]"
    ru = "[Select_CString(CHARACTER.IsFemale, 'Королева', 'Король')] заката"
    assert "brackets_mismatch" in qa.check_unit(en, ru)
    ck3_ru = qa_rules.resolve({"preset": "ck3_ru"})
    assert "brackets_mismatch" not in qa.check_unit(en, ru, ruleset=ck3_ru)


def test_quiet_preset_keeps_only_what_breaks_the_game() -> None:
    quiet = qa_rules.resolve({"preset": "quiet"})
    assert "dollar_mismatch" in quiet.active_ids()
    assert "edge_space" not in quiet.active_ids()
    # но и в нём потерянная переменная остаётся ошибкой
    assert qa.check_unit("Cost: $V$", "Цена", ruleset=quiet) == ["dollar_mismatch"]


def test_strict_preset_turns_everything_on() -> None:
    strict = qa_rules.resolve({"preset": "strict"})
    assert strict.active_ids() == {r.id for r in qa_rules.BUILTIN_RULES}


# --- запись дельты -------------------------------------------------------


def test_overlay_records_only_the_difference() -> None:
    rules = qa_rules.default_ruleset()
    edited = rules.with_rule(
        rules.get("len_ratio").with_params(min_ratio=0.3))
    overlay = qa_rules.make_overlay(qa_rules.CUSTOM, edited)
    assert overlay["rules"] == {"len_ratio": {"params": {"min_ratio": 0.3}}}


def test_overlay_over_a_preset_does_not_copy_the_preset() -> None:
    """Иначе набор застыл бы: правку пресета в новой версии проект не увидит."""
    rules = qa_rules.resolve({"preset": "ck3_ru"})
    overlay = qa_rules.make_overlay("ck3_ru", rules)
    assert overlay["rules"] == {}
    # прежнее имя понято, но записано нынешнее: файлы не должны плодить старое
    assert overlay["preset"] == "ck3"


def test_project_overlay_does_not_copy_global_edits() -> None:
    glob = {"rules": {"len_ratio": {"enabled": True}}}
    rules = qa_rules.resolve(glob)
    overlay = qa_rules.make_overlay(qa_rules.CUSTOM, rules, under=glob)
    assert overlay["rules"] == {}


def test_overlay_round_trips_through_json_and_resolve() -> None:
    # как это делает пользователь: выбрал набор, потом правит правило
    rules = qa_rules.resolve({"preset": "ck3_ru"})
    edited = rules.with_rule(qa_rules.replace(
        rules.get("same_as_en"), enabled=False, severity=qa_rules.INFO))
    overlay = json.loads(json.dumps(
        qa_rules.make_overlay("ck3_ru", edited), ensure_ascii=False))
    assert set(overlay["rules"]) == {"same_as_en"}      # только правка, не весь набор

    restored = qa_rules.resolve(overlay)
    assert not restored.get("same_as_en").enabled
    assert restored.severity("same_as_en") == qa_rules.INFO
    # и пресет доехал вместе с правкой
    assert restored.get("inconsistent").severity == qa_rules.INFO


def test_empty_overlay_is_recognised_and_not_stored() -> None:
    assert qa_rules.is_empty_overlay(None)
    assert qa_rules.is_empty_overlay({"version": 1, "preset": None, "rules": {}})
    assert not qa_rules.is_empty_overlay({"preset": "quiet"})


# --- слой внутри файла проекта ------------------------------------------


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

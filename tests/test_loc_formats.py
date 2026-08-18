"""Реестр форматов: какой парсер применить к этим файлам.

Формат определяется по содержимому дерева, а не по названию игры, — иначе
своя игра, заведённая свободным именем, оставалась бы без ответа. Здесь и
проверяется, что ответ берётся из данных и что оба формата отвечают одинаково
устроенным набором функций.
"""
from __future__ import annotations

import pytest

from pdxloc.core import loc_formats, paradox_csv, paradox_yaml
from pdxloc.core.models import LocEntry

YML_TEXT = 'l_english:\n key:0 "Hello"\n'
CSV_TEXT = ("#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;;;x\n"
            "key;Hello;Bonjour;Hallo;;Hola;;;;;;;;;x\n")


@pytest.fixture
def yml_tree(tmp_path):
    root = tmp_path / "yml"
    root.mkdir()
    (root / "mod_l_english.yml").write_text(YML_TEXT, encoding="utf-8-sig")
    return root


@pytest.fixture
def csv_tree(tmp_path):
    root = tmp_path / "csv"
    root.mkdir()
    (root / "text.csv").write_text(CSV_TEXT, encoding="cp1252")
    return root


def test_the_format_is_told_by_the_tree(yml_tree, csv_tree, tmp_path) -> None:
    assert loc_formats.detect(yml_tree) == loc_formats.YML
    assert loc_formats.detect(csv_tree) == loc_formats.CSV

    empty = tmp_path / "empty"
    empty.mkdir()
    assert loc_formats.detect(empty) == loc_formats.DEFAULT
    assert loc_formats.detect(tmp_path / "нет такой папки") == loc_formats.DEFAULT


def test_a_yml_file_without_a_header_is_not_localisation(tmp_path) -> None:
    """`.yml` рядом с модом бывает и настройкой сборки — заголовок решает."""
    root = tmp_path / "ci"
    root.mkdir()
    (root / "workflow.yml").write_text("name: build\non: push\n", encoding="utf-8")
    assert not paradox_yaml.detect(root)
    assert loc_formats.detect(root) == loc_formats.DEFAULT


def test_an_unknown_id_falls_back_to_the_current_format() -> None:
    """Значение приезжает из файла проекта — версия могла знать больше нас."""
    assert loc_formats.get("никакой").id == loc_formats.DEFAULT
    assert loc_formats.get(loc_formats.CSV).id == loc_formats.CSV


def test_both_formats_answer_the_same_questions(yml_tree, csv_tree) -> None:
    """Вызывающие ходят только через эти имена — набор обязан совпадать."""
    for fmt, root, language in ((loc_formats.get(loc_formats.YML), yml_tree, "english"),
                                (loc_formats.get(loc_formats.CSV), csv_tree, "english")):
        found = fmt.files(root, language)
        assert len(found) == 1
        loc = fmt.parse_file(found[0], language=language,
                             encoding=fmt.encodings[0])
        assert [e.text for e in loc.entries] == ["Hello"]
        assert fmt.render(language, loc.entries, loc.trailing)
        assert isinstance(fmt.escape_value("a\nb"), str)
        assert isinstance(fmt.map_relpath("x", "english", "russian"), str)


def test_the_language_lives_in_the_path_only_in_the_current_format() -> None:
    """У старых игр язык — колонка, и файл перевода зовётся как оригинал."""
    yml = loc_formats.get(loc_formats.YML)
    csv = loc_formats.get(loc_formats.CSV)
    assert yml.language_in_path and not csv.language_in_path
    assert yml.map_relpath("english/a_l_english.yml", "english", "russian") == \
        "russian/a_l_russian.yml"
    assert csv.map_relpath("HolyFury.csv", "english", "russian") == "HolyFury.csv"


def test_the_registry_delegates_to_the_module(monkeypatch, yml_tree) -> None:
    """Формат держит модуль, а не снятые ссылки: подмена обязана доходить.

    Проверка не про тесты, а про устройство: ссылка на функцию, снятая при
    импорте, не узнала бы ни о подмене, ни о том, что модуль перезагрузили.
    """
    calls: list = []
    real = paradox_yaml.parse_file
    monkeypatch.setattr(paradox_yaml, "parse_file",
                        lambda p, **kw: (calls.append(p), real(p, **kw))[1])
    fmt = loc_formats.get(loc_formats.YML)
    fmt.parse_file(next(iter(fmt.files(yml_tree, "english"))), language="english")
    assert len(calls) == 1


def test_newlines_are_normalised_the_same_for_both() -> None:
    """В базу перевод ложится в общем виде: настоящий перенос ломает оба формата."""
    assert loc_formats.normalize_newlines("раз\nдва") == "раз\\nдва"
    assert paradox_csv.escape_value("раз\nдва") == "раз\\nдва"


def test_csv_render_needs_no_raw_for_a_fresh_entry() -> None:
    entry = LocEntry(key="k", version="", text="Текст")
    assert loc_formats.get(loc_formats.CSV).render("russian", [entry]) == "k;Текст;x\n"

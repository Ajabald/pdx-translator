"""The registry of formats: which parser to apply to these files.

The format is decided by the content of the tree and not by the name of the game
— otherwise a game of one's own, set up with a free name, would be left without an
answer. Here we check that the answer is taken from the data and that both formats
answer with an identically built set of functions.
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
    """A `.yml` next to a mod happens to be a build setting too — the header decides."""
    root = tmp_path / "ci"
    root.mkdir()
    (root / "workflow.yml").write_text("name: build\non: push\n", encoding="utf-8")
    assert not paradox_yaml.detect(root)
    assert loc_formats.detect(root) == loc_formats.DEFAULT


def test_an_unknown_id_falls_back_to_the_current_format() -> None:
    """The value arrives from a project file — the version could have known more than we do."""
    assert loc_formats.get("никакой").id == loc_formats.DEFAULT
    assert loc_formats.get(loc_formats.CSV).id == loc_formats.CSV


def test_both_formats_answer_the_same_questions(yml_tree, csv_tree) -> None:
    """The callers go only by these names — the set is obliged to match."""
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
    """In the older games the language is a column, and the translation file is named like the original."""
    yml = loc_formats.get(loc_formats.YML)
    csv = loc_formats.get(loc_formats.CSV)
    assert yml.language_in_path and not csv.language_in_path
    assert yml.map_relpath("english/a_l_english.yml", "english", "russian") == \
        "russian/a_l_russian.yml"
    assert csv.map_relpath("HolyFury.csv", "english", "russian") == "HolyFury.csv"


def test_the_registry_delegates_to_the_module(monkeypatch, yml_tree) -> None:
    """A format holds the module and not references taken off it: a substitution is obliged to reach it.

    The check is not about the tests but about the arrangement: a reference to a
    function taken at import time would learn neither of a substitution nor of the
    module being reloaded.
    """
    calls: list = []
    real = paradox_yaml.parse_file
    monkeypatch.setattr(paradox_yaml, "parse_file",
                        lambda p, **kw: (calls.append(p), real(p, **kw))[1])
    fmt = loc_formats.get(loc_formats.YML)
    fmt.parse_file(next(iter(fmt.files(yml_tree, "english"))), language="english")
    assert len(calls) == 1


def test_newlines_are_normalised_the_same_for_both() -> None:
    """Into the database a translation goes in the common form: a real line break breaks both formats."""
    assert loc_formats.normalize_newlines("раз\nдва") == "раз\\nдва"
    assert paradox_csv.escape_value("раз\nдва") == "раз\\nдва"


def test_csv_render_needs_no_raw_for_a_fresh_entry() -> None:
    entry = LocEntry(key="k", version="", text="Текст")
    assert loc_formats.get(loc_formats.CSV).render("russian", [entry]) == "k;Текст;x\n"

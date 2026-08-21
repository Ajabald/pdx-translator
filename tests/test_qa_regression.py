"""A regression of the quality checks on live data.

The former rule set gave 1097 messages, 827 of them «errors», and 826 of those
were false: the rule demanded closing #weak at the end of a row, though that is
how the original of the mod itself is built. The test pins down that this no
longer happens.
"""
from __future__ import annotations


import pytest

from pdxloc.core.qa import CODES, check_unit, run_qa
from pdxloc.core.paradox_yaml import parse_file

from conftest import REALDATA_EN, REALDATA_RU, realdata_available

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA"),
]


@pytest.fixture(scope="module")
def real_pairs():
    """The pairs «original — translation» straight from the files of the mod, without a DB."""
    pairs = []
    for en_path in REALDATA_EN.rglob("*.yml"):
        if "_l_english" not in en_path.name:
            continue
        rel = en_path.relative_to(REALDATA_EN).as_posix()
        ru_path = REALDATA_RU / rel.replace("_l_english", "_l_russian")
        if not ru_path.is_file():
            continue
        en_entries = {e.key: e.text for e in parse_file(en_path).entries}
        for entry in parse_file(ru_path).entries:
            en_text = en_entries.get(entry.key)
            if (en_text and entry.text and entry.text != en_text
                    and "ТРЕБУЕТ ПЕРЕВОДА" not in entry.comment_inline):
                pairs.append((entry.key, en_text, entry.text))
    assert len(pairs) > 3000, "ожидались тысячи переведённых строк"
    return pairs


def test_errors_are_rare_and_real(real_pairs):
    """There have to be single errors, not hundreds."""
    errors = []
    for key, en, ru in real_pairs:
        for code in check_unit(en, ru):
            if CODES[code][0] == "error":
                errors.append((key, code))
    assert len(errors) < 10, f"слишком много ошибок: {errors[:10]}"


def test_unclosed_tags_no_longer_flagged(real_pairs):
    """Rows with #weak and no #! — the most massive case — are no longer an error."""
    suspects = [
        (key, en, ru) for key, en, ru in real_pairs
        if "#weak" in en and "#!" not in en
    ]
    assert suspects, "в моде есть такие строки — иначе тест бессмысленен"
    for key, en, ru in suspects:
        codes = check_unit(en, ru)
        assert "fmt_broken" not in codes, f"{key}: ложная ошибка на незакрытом теге"
        assert "fmt_mismatch" not in codes or "#" not in ru, key


def test_total_noise_dropped(real_pairs):
    """The total volume of messages fell severalfold (it was 1097)."""
    total = sum(len(check_unit(en, ru)) for _key, en, ru in real_pairs)
    assert total < 300, f"проверки снова шумят: {total} сообщений"


def test_paragraph_breaks_are_not_double_spaces(real_pairs):
    """A regression: a paragraph break was declared a double space.

    The rule replaced every line break (two characters: a backslash and an «n»)
    with a space, so `\\n\\n` looked like two spaces in a row. On a live mod 84
    translations out of 4851 were marked that way — every single one of them
    falsely, there are no real double spaces in the translations at all.
    """
    with_breaks = [(k, en, ru) for k, en, ru in real_pairs if "\\n\\n" in ru]
    assert with_breaks, "в моде есть абзацные разрывы — иначе тест бессмысленен"
    for key, en, ru in with_breaks:
        assert "double_space" not in check_unit(en, ru), key


def test_typographic_checks_do_not_invent_problems(real_pairs):
    """The rules about spaces and quotes keep quiet on a proofread text.

    Should something start firing here — first look at the row with your own eyes:
    it is either a real typo of the translator or a false rule again.
    """
    noisy = {code: [] for code in ("double_space", "edge_space", "unbalanced_quotes")}
    for key, en, ru in real_pairs:
        for code in check_unit(en, ru):
            if code in noisy:
                noisy[code].append(key)
    assert not any(noisy.values()), {k: v[:5] for k, v in noisy.items() if v}


def test_ignored_issue_disappears(db):
    """What is marked «not an error» is no longer shown."""
    from pdxloc.core import qa

    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1,1,'f_l_english.yml')")
    db.execute(
        "INSERT INTO units (id, file_id, key, en_text, ru_text, status) "
        "VALUES (1, 1, 'k', 'Text here', 'Текст  здесь', 'translated')")
    db.commit()

    issues = run_qa(db, 1)
    assert [i.code for i in issues] == ["double_space"]
    qa.ignore_issue(db, 1, "double_space")
    assert run_qa(db, 1) == []
    qa.unignore_issue(db, 1, "double_space")
    assert len(run_qa(db, 1)) == 1


def test_inconsistent_translations_detected(db):
    """One and the same original translated differently is a real problem."""
    from pdxloc.core import tm

    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1,1,'f_l_english.yml')")
    h = tm.en_hash("Never Conquered")
    for i, ru in enumerate(("Непокорённые", "Непобеждённые"), start=1):
        db.execute(
            "INSERT INTO units (id, file_id, key, en_text, en_hash, ru_text, status) "
            "VALUES (?, 1, ?, 'Never Conquered', ?, ?, 'translated')", (i, f"k{i}", h, ru))
    db.commit()

    codes = [i.code for i in run_qa(db, 1)]
    assert codes.count("inconsistent") == 2
    assert "Непокорённые" in next(i.message for i in run_qa(db, 1) if i.code == "inconsistent")

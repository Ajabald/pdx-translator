"""Регрессия проверок качества на живых данных.

Прежний набор правил давал 1097 сообщений, из них 827 «ошибок», и 826 из них
были ложными: правило требовало закрывать #weak в конце строки, хотя так
устроен сам оригинал мода. Тест фиксирует, что этого больше не происходит.
"""
from __future__ import annotations

import sqlite3

import pytest

from ck3loc.core.qa import CODES, check_unit, run_qa
from ck3loc.core.paradox_yaml import parse_file

from conftest import REALDATA_EN, REALDATA_RU, realdata_available

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA"),
]


@pytest.fixture(scope="module")
def real_pairs():
    """Пары «оригинал — перевод» прямо из файлов мода, без БД."""
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
    """Ошибок должно быть единицы, а не сотни."""
    errors = []
    for key, en, ru in real_pairs:
        for code in check_unit(en, ru):
            if CODES[code][0] == "error":
                errors.append((key, code))
    assert len(errors) < 10, f"слишком много ошибок: {errors[:10]}"


def test_unclosed_tags_no_longer_flagged(real_pairs):
    """Строки с #weak без #! — самый массовый случай — больше не ошибка."""
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
    """Общий объём сообщений упал в разы (было 1097)."""
    total = sum(len(check_unit(en, ru)) for _key, en, ru in real_pairs)
    assert total < 300, f"проверки снова шумят: {total} сообщений"


def test_new_checks_find_real_problems(real_pairs):
    """Новые правила ловят настоящие огрехи, а не выдумывают их."""
    found = {code: 0 for code in ("double_space", "edge_space", "unbalanced_quotes")}
    for _key, en, ru in real_pairs:
        for code in check_unit(en, ru):
            if code in found:
                found[code] += 1
    assert found["double_space"] > 0, "двойные пробелы в переводах точно есть"


def test_ignored_issue_disappears(db):
    """Помеченное как «не ошибка» больше не показывается."""
    from ck3loc.core import qa

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
    """Один и тот же оригинал, переведённый по-разному, — реальная проблема."""
    from ck3loc.core import tm

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

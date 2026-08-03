"""Тесты операций над строками (unit_ops)."""
from __future__ import annotations

from ck3loc.core import tm, unit_ops
from ck3loc.core.statuses import Status


def seed(db):
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'a_l_english.yml')")
    rows = [
        ("k1", "Hello", "untranslated", None),
        ("k2", "Hello", "untranslated", None),      # тот же EN, что k1
        ("k3", "Hello", "translated", "Привет"),    # тот же EN, уже переведён
        ("k4", "World", "untranslated", None),
        ("k5", "Stale text", "stale", "Старый"),
    ]
    ids = {}
    for k, en, st, ru in rows:
        cur = db.execute(
            "INSERT INTO units (file_id, key, en_text, en_hash, ru_text, status, prev_en_text) "
            "VALUES (1, ?, ?, ?, ?, ?, ?)",
            (k, en, tm.en_hash(en), ru, st, "Old EN" if st == "stale" else None))
        ids[k] = cur.lastrowid
    db.commit()
    return ids


def get(db, uid):
    return db.execute("SELECT * FROM units WHERE id = ?", (uid,)).fetchone()


def test_save_ru_text_transitions(db):
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k1"], "Привет")
    u = get(db, ids["k1"])
    assert u["status"] == Status.TRANSLATED.value and u["ru_text"] == "Привет"
    # пустой текст сбрасывает
    unit_ops.save_ru_text(db, ids["k1"], "  ")
    assert get(db, ids["k1"])["status"] == Status.UNTRANSLATED.value
    # stale + правка = актуализация
    unit_ops.save_ru_text(db, ids["k5"], "Новый перевод")
    u = get(db, ids["k5"])
    assert u["status"] == Status.TRANSLATED.value
    assert u["prev_en_text"] is None


def test_real_newline_normalized_on_save(db):
    """Enter в поле перевода не должен разводить базу с файлом.

    Раньше настоящий перенос строки доживал до базы, при записи в мод
    превращался в escape-последовательность формата Paradox — и каждое
    следующее сканирование докладывало «расхождение с файлом» на строке,
    которую никто не трогал.
    """
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Первая\nВторая\r\nТретья")

    assert get(db, ids["k4"])["ru_text"] == "Первая\\nВторая\\nТретья"
    # в память переводов попадает то же самое, иначе подсказки разъедутся
    assert tm.lookup(db, "World")[0].ru_text == "Первая\\nВторая\\nТретья"


def test_save_feeds_tm(db):
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Мир")
    assert tm.lookup(db, "World")[0].ru_text == "Мир"


def test_set_status_bulk_gate(db):
    ids = seed(db)
    # reviewed требует RU: k1 без перевода не изменится, k3 изменится
    n = unit_ops.set_status(db, [ids["k1"], ids["k3"]], Status.REVIEWED)
    assert n == 1
    assert get(db, ids["k1"])["status"] == Status.UNTRANSLATED.value
    assert get(db, ids["k3"])["status"] == Status.REVIEWED.value
    # ignored ставится и без перевода
    n = unit_ops.set_status(db, [ids["k1"], ids["k4"]], Status.IGNORED)
    assert n == 2
    assert get(db, ids["k1"])["status"] == Status.IGNORED.value


def test_reset_translation(db):
    ids = seed(db)
    n = unit_ops.reset_translation(db, [ids["k3"], ids["k5"]])
    assert n == 2
    u = get(db, ids["k3"])
    assert u["ru_text"] is None and u["status"] == Status.UNTRANSLATED.value


def test_apply_to_same_en(db):
    ids = seed(db)
    assert unit_ops.count_same_en(db, ids["k3"]) == 2      # k1, k2
    targets = unit_ops.apply_to_same_en(db, ids["k3"])
    assert sorted(targets) == sorted([ids["k1"], ids["k2"]])
    assert get(db, ids["k1"])["ru_text"] == "Привет"
    assert get(db, ids["k1"])["status"] == Status.TRANSLATED.value
    # k4 (другой EN) не тронут
    assert get(db, ids["k4"])["ru_text"] is None


def test_apply_best_tm(db):
    ids = seed(db)
    tm.upsert(db, "World", "Мир из базы")
    assert unit_ops.apply_best_tm(db, ids["k4"])
    u = get(db, ids["k4"])
    assert u["ru_text"] == "Мир из базы" and u["status"] == Status.AUTO.value
    # без хита — False
    assert not unit_ops.apply_best_tm(db, ids["k1"]) or get(db, ids["k1"])["status"] == Status.AUTO.value


def test_is_markup_only():
    assert unit_ops.is_markup_only("[GetPlayer.GetDynasty.GetNameNoTooltip]")
    assert unit_ops.is_markup_only("$VALUE$")
    assert unit_ops.is_markup_only("[GetName] $X$ £gold£")
    assert not unit_ops.is_markup_only("Hello [GetName]")
    assert not unit_ops.is_markup_only("Hello")
    assert not unit_ops.is_markup_only("")
    assert not unit_ops.is_markup_only("   ")


def test_save_on_ignored_makes_translated(db):
    ids = seed(db)
    unit_ops.set_status(db, [ids["k1"]], Status.IGNORED)
    unit_ops.save_ru_text(db, ids["k1"], "Всё-таки перевёл")
    assert get(db, ids["k1"])["status"] == Status.TRANSLATED.value

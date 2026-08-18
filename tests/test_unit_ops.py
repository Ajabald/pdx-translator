"""Тесты операций над строками (unit_ops)."""
from __future__ import annotations

import re
from pathlib import Path

from pdxloc.core import tm, unit_ops
from pdxloc.core.statuses import Status

SRC = Path(unit_ops.__file__).resolve().parents[1]

# Кто, кроме unit_ops, вправе трогать перевод строки — и почему.
#
#   scanner.py    — обновляет EN-сторону и заполняет пустые строки из файлов
#                   перевода; правки человека сюда не попадают;
#   tm.py         — `bulk_apply` заполняет только пустые непереведённые строки,
#                   затирать ему нечего;
#   db.py         — миграции схемы, там таблица пересобирается целиком;
#   loc_import.py — пишет пачкой ради скорости (построчный `save_ru_text` стоил
#                   одного fsync на строку), но перед записью зовёт
#                   `record_history` и `status_after_edit` — то есть выполняет
#                   ровно то требование, ради которого этот сторож заведён.
_MAY_WRITE_TRANSLATIONS = {"unit_ops.py", "scanner.py", "tm.py", "db.py",
                           "loc_import.py"}
_WRITES_RU = re.compile(r"UPDATE units SET[^\"']*ru_text", re.IGNORECASE)


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


def test_status_table_is_the_same_for_a_batch_and_for_a_single_edit():
    """Таблица переходов одна на оба пути записи — построчный и пакетный.

    Импорт перевода из мода пишет пачкой и зовёт ту же `status_after_edit`, что
    и правка в поле. Разойдись они — импорт оставлял бы строки в состояниях,
    которых не бывает при ручной правке, и заметить это можно было бы только
    глазами, на чужом моде.
    """
    after = unit_ops.status_after_edit

    # пустой текст сбрасывает всё, чем строка была заполнена
    for was in (Status.TRANSLATED, Status.REVIEWED, Status.AUTO,
                Status.MACHINE, Status.CUSTOM):
        assert after(was.value, None, "было", None, None)[0] == Status.UNTRANSLATED.value
    # а «игнорируется» стиранием не трогаем: там решение уже принято
    assert after(Status.IGNORED.value, None, None, None, None)[0] == Status.IGNORED.value

    # правка снимает «машинный» и «авто» — иначе строка не уехала бы в мод
    for was in (Status.UNTRANSLATED, Status.AUTO, Status.MACHINE, Status.IGNORED):
        assert after(was.value, "Перевод", None, None, None)[0] == Status.TRANSLATED.value

    # устарело + другой текст = актуализация, дифф больше не нужен
    status, prev, kind = after(
        Status.STALE.value, "Новый", "Старый", "Old EN", "cosmetic")
    assert (status, prev, kind) == (Status.TRANSLATED.value, None, None)

    # тот же текст при «устарело» ничего не актуализирует, дифф остаётся
    status, prev, kind = after(
        Status.STALE.value, "Старый", "Старый", "Old EN", "cosmetic")
    assert (status, prev, kind) == (Status.STALE.value, "Old EN", "cosmetic")

    # «проверено» правка не понижает
    assert after(Status.REVIEWED.value, "Правка", "Было", None, None)[0] == \
        Status.REVIEWED.value


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


def test_apply_to_same_en_is_undoable(db):
    """Ctrl+Z обязан снимать её целиком: правка задевает сотни строк разом.

    Среди целей есть строки со статусом «Авто» — там перевод уже стоял, и
    затирать его безвозвратно нельзя.
    """
    ids = seed(db)
    db.execute("UPDATE units SET ru_text = 'Из памяти', status = ? WHERE id = ?",
               (Status.AUTO.value, ids["k1"]))
    db.commit()

    batch = unit_ops.new_batch_id()
    targets = unit_ops.apply_to_same_en(db, ids["k3"], batch_id=batch)
    assert get(db, ids["k1"])["ru_text"] == "Привет"

    assert unit_ops.last_batch(db)[0] == batch          # операция видна Ctrl+Z
    assert unit_ops.undo_batch(db, batch) == len(targets)
    restored = get(db, ids["k1"])
    assert restored["ru_text"] == "Из памяти"
    assert restored["status"] == Status.AUTO.value


def test_apply_best_tm(db):
    ids = seed(db)
    tm.upsert(db, "World", "Мир из базы")
    assert unit_ops.apply_best_tm(db, ids["k4"])
    u = get(db, ids["k4"])
    assert u["ru_text"] == "Мир из базы" and u["status"] == Status.AUTO.value
    # без хита — False
    assert not unit_ops.apply_best_tm(db, ids["k1"]) or get(db, ids["k1"])["status"] == Status.AUTO.value


def test_filling_from_memory_leaves_a_history_record(db):
    """Подстановка затирает то, что было, — редакция обязана остаться."""
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Мой перевод")
    tm.upsert(db, "World", "Мир из базы")

    assert unit_ops.apply_best_tm(db, ids["k4"])

    texts = [r["ru_text"] for r in unit_ops.unit_history(db, ids["k4"])]
    assert "Мой перевод" in texts


def test_translations_are_written_only_where_history_is_kept():
    """Перевод правит `unit_ops` — он же кладёт редакцию в историю.

    Ctrl+Z держится на этом: правка мимо `record_history` откатиться не может,
    и заметить такую мимо-запись можно только когда пользователь попробует
    отменить массовую операцию и ничего не произойдёт. Так уже случилось с
    «применить ко всем строкам с таким же оригиналом».
    """
    hits = [
        f"{path.relative_to(SRC).as_posix()}:{n}"
        for path in sorted(SRC.rglob("*.py"))
        if path.name not in _MAY_WRITE_TRANSLATIONS
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _WRITES_RU.search(line)
    ]
    assert not hits, (
        "Перевод записывается мимо unit_ops — Ctrl+Z такую правку не снимет:\n"
        + "\n".join(hits))


def test_is_markup_only():
    assert unit_ops.is_markup_only("[GetPlayer.GetDynasty.GetNameNoTooltip]")
    assert unit_ops.is_markup_only("$VALUE$")
    assert unit_ops.is_markup_only("[GetName] $X$ £gold£")
    assert not unit_ops.is_markup_only("Hello [GetName]")
    assert not unit_ops.is_markup_only("Hello")
    assert not unit_ops.is_markup_only("")
    assert not unit_ops.is_markup_only("   ")


def test_has_nothing_to_translate():
    """Пустое значение — та же категория, что голый тег: переводить нечего.

    Отдельный предикат, а не расширение `is_markup_only`: та отвечает на вопрос
    «строка ИЗ разметки», и пустую строка ею не считает — на этом стоит
    подсветка. Здесь вопрос другой.
    """
    assert unit_ops.has_nothing_to_translate("")
    assert unit_ops.has_nothing_to_translate("   ")
    assert unit_ops.has_nothing_to_translate(None)
    assert unit_ops.has_nothing_to_translate("[GetPlayer.GetDynasty.GetNameNoTooltip]")
    assert unit_ops.has_nothing_to_translate("$VALUE$ £gold£")
    assert not unit_ops.has_nothing_to_translate("Hello")
    assert not unit_ops.has_nothing_to_translate("Hello [GetName]")


def test_save_on_ignored_makes_translated(db):
    ids = seed(db)
    unit_ops.set_status(db, [ids["k1"]], Status.IGNORED)
    unit_ops.save_ru_text(db, ids["k1"], "Всё-таки перевёл")
    assert get(db, ids["k1"])["status"] == Status.TRANSLATED.value

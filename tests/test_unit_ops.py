"""Tests of the operations over rows (unit_ops)."""
from __future__ import annotations

import re
from pathlib import Path

from pdxloc.core import tm, unit_ops
from pdxloc.core.statuses import Status

SRC = Path(unit_ops.__file__).resolve().parents[1]

# Who, apart from unit_ops, is entitled to touch the translation of a row — and why.
#
#   scanner.py    — refreshes the EN side and fills empty rows from the files of
#                   the translation; the edits of a human do not get here;
#   tm.py         — `bulk_apply` fills only the empty untranslated rows, it has
#                   nothing to overwrite;
#   db.py         — the schema migrations, where the table is rebuilt whole;
#   loc_import.py — writes in batches for the sake of speed (a row-by-row
#                   `save_ru_text` cost one fsync per row), but before writing it
#                   calls `record_history` and `status_after_edit` — that is, it
#                   meets the very demand this watchman was set up for.
_MAY_WRITE_TRANSLATIONS = {"unit_ops.py", "scanner.py", "tm.py", "db.py",
                           "loc_import.py"}
_WRITES_RU = re.compile(r"UPDATE units SET[^\"']*ru_text", re.IGNORECASE)


def seed(db):
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'a_l_english.yml')")
    rows = [
        ("k1", "Hello", "untranslated", None),
        ("k2", "Hello", "untranslated", None),      # the same EN as k1
        ("k3", "Hello", "translated", "Привет"),    # the same EN, already translated
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
    # an empty text resets it
    unit_ops.save_ru_text(db, ids["k1"], "  ")
    assert get(db, ids["k1"])["status"] == Status.UNTRANSLATED.value
    # stale + an edit = actualisation
    unit_ops.save_ru_text(db, ids["k5"], "Новый перевод")
    u = get(db, ids["k5"])
    assert u["status"] == Status.TRANSLATED.value
    assert u["prev_en_text"] is None


def test_status_table_is_the_same_for_a_batch_and_for_a_single_edit():
    """The transition table is one for both paths of writing — row-by-row and batch.

    Importing a translation from a mod writes in batches and calls the same
    `status_after_edit` as an edit in the field. Let them diverge — and the import
    would leave rows in states that never arise from a manual edit, and noticing
    that would only be possible by eye, on somebody else's mod.
    """
    after = unit_ops.status_after_edit

    # an empty text resets everything the row was filled with
    for was in (Status.TRANSLATED, Status.REVIEWED, Status.AUTO,
                Status.MACHINE, Status.CUSTOM):
        assert after(was.value, None, "было", None, None)[0] == Status.UNTRANSLATED.value
    # while «ignored» we do not touch by erasing: the decision there is already made
    assert after(Status.IGNORED.value, None, None, None, None)[0] == Status.IGNORED.value

    # an edit takes «machine» and «auto» off — otherwise the row would not travel to the mod
    for was in (Status.UNTRANSLATED, Status.AUTO, Status.MACHINE, Status.IGNORED):
        assert after(was.value, "Перевод", None, None, None)[0] == Status.TRANSLATED.value

    # stale + a different text = actualisation, the diff is no longer needed
    status, prev, kind = after(
        Status.STALE.value, "Новый", "Старый", "Old EN", "cosmetic")
    assert (status, prev, kind) == (Status.TRANSLATED.value, None, None)

    # the same text at «stale» actualises nothing, the diff stays
    status, prev, kind = after(
        Status.STALE.value, "Старый", "Старый", "Old EN", "cosmetic")
    assert (status, prev, kind) == (Status.STALE.value, "Old EN", "cosmetic")

    # «reviewed» an edit does not lower
    assert after(Status.REVIEWED.value, "Правка", "Было", None, None)[0] == \
        Status.REVIEWED.value


def test_real_newline_normalized_on_save(db):
    """Enter in the translation field must not part the database from the file.

    A real line break used to live through to the database, at the write into the
    mod it turned into an escape sequence of the Paradox format — and every next
    scan reported a «divergence with the file» on a row nobody had touched.
    """
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Первая\nВторая\r\nТретья")

    assert get(db, ids["k4"])["ru_text"] == "Первая\\nВторая\\nТретья"
    # the same thing goes into the translation memory, otherwise the hints diverge
    assert tm.lookup(db, "World")[0].ru_text == "Первая\\nВторая\\nТретья"


def test_save_feeds_tm(db):
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Мир")
    assert tm.lookup(db, "World")[0].ru_text == "Мир"


def test_set_status_bulk_gate(db):
    ids = seed(db)
    # reviewed demands RU: k1 without a translation will not change, k3 will
    n = unit_ops.set_status(db, [ids["k1"], ids["k3"]], Status.REVIEWED)
    assert n == 1
    assert get(db, ids["k1"])["status"] == Status.UNTRANSLATED.value
    assert get(db, ids["k3"])["status"] == Status.REVIEWED.value
    # ignored is set even without a translation
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
    # k4 (a different EN) is untouched
    assert get(db, ids["k4"])["ru_text"] is None


def test_apply_to_same_en_is_undoable(db):
    """Ctrl+Z is obliged to take it off whole: the edit touches hundreds of rows at once.

    Among the targets there are rows with the status «Auto» — there a translation
    already stood, and overwriting it beyond recall will not do.
    """
    ids = seed(db)
    db.execute("UPDATE units SET ru_text = 'Из памяти', status = ? WHERE id = ?",
               (Status.AUTO.value, ids["k1"]))
    db.commit()

    batch = unit_ops.new_batch_id()
    targets = unit_ops.apply_to_same_en(db, ids["k3"], batch_id=batch)
    assert get(db, ids["k1"])["ru_text"] == "Привет"

    assert unit_ops.last_batch(db)[0] == batch          # the operation is visible to Ctrl+Z
    assert unit_ops.undo_batch(db, batch) == len(targets)
    restored = get(db, ids["k1"])
    assert restored["ru_text"] == "Из памяти"
    assert restored["status"] == Status.AUTO.value


def test_undo_brings_back_the_diff_not_just_the_status(db):
    """The undo brings back WHAT the row went stale by, too.

    The history used to keep only the text and the status: after Ctrl+Z the row
    became «Stale» again, but `prev_en_text` was lost — the diff vanished, and the
    human was left with a red row and no explanation of what is wanted of them.
    """
    ids = seed(db)
    stale = ids["k5"]
    assert get(db, stale)["prev_en_text"] == "Old EN"

    db.execute("UPDATE units SET change_kind = 'meaning' WHERE id = ?", (stale,))
    db.commit()

    batch = unit_ops.new_batch_id()
    unit_ops.record_history(db, [stale], origin="manual", batch_id=batch)
    # actualisation: the translation is confirmed, the diff is no longer needed
    unit_ops.save_ru_text(db, stale, "Новый перевод")
    db.execute("UPDATE units SET prev_en_text = NULL, change_kind = NULL WHERE id = ?",
               (stale,))
    db.commit()
    assert get(db, stale)["prev_en_text"] is None

    unit_ops.undo_batch(db, batch)

    back = get(db, stale)
    assert back["ru_text"] == "Старый"
    assert back["status"] == Status.STALE.value
    assert back["prev_en_text"] == "Old EN", "дифф не вернулся вместе со статусом"
    assert back["change_kind"] == "meaning"


def test_history_of_a_fresh_row_carries_no_diff(db):
    """A row that is not stale has no diff, and there is no point inventing one for the undo."""
    ids = seed(db)
    batch = unit_ops.new_batch_id()
    unit_ops.record_history(db, [ids["k3"]], batch_id=batch)

    row = db.execute(
        "SELECT prev_en_text, change_kind FROM unit_history WHERE batch_id = ?",
        (batch,)).fetchone()
    assert row["prev_en_text"] is None and row["change_kind"] is None


def test_apply_best_tm(db):
    ids = seed(db)
    tm.upsert(db, "World", "Мир из базы")
    assert unit_ops.apply_best_tm(db, ids["k4"])
    u = get(db, ids["k4"])
    assert u["ru_text"] == "Мир из базы" and u["status"] == Status.AUTO.value
    # without a hit — False
    assert not unit_ops.apply_best_tm(db, ids["k1"]) or get(db, ids["k1"])["status"] == Status.AUTO.value


def test_filling_from_memory_leaves_a_history_record(db):
    """The substitution overwrites what was there — the revision is obliged to stay."""
    ids = seed(db)
    unit_ops.save_ru_text(db, ids["k4"], "Мой перевод")
    tm.upsert(db, "World", "Мир из базы")

    assert unit_ops.apply_best_tm(db, ids["k4"])

    texts = [r["ru_text"] for r in unit_ops.unit_history(db, ids["k4"])]
    assert "Мой перевод" in texts


def test_translations_are_written_only_where_history_is_kept():
    """The translation is edited by `unit_ops` — it also puts the revision into the history.

    Ctrl+Z rests on that: an edit past `record_history` cannot be undone, and
    noticing such a write-past is only possible when the user tries to undo a bulk
    operation and nothing happens. That has already happened with «apply to all
    rows with the same original».
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
    """An empty value is the same category as a bare tag: there is nothing to translate.

    A predicate of its own and not an extension of `is_markup_only`: that one
    answers the question "is the row MADE of markup", and an empty row it does not
    count as such — the highlighting rests on that. Here the question is another.
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

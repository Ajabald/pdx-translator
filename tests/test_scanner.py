"""Tests of the diff machine of the scanner: one per transition."""
from __future__ import annotations


from pdxloc.core.paradox_yaml import map_relpath
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status


def make_project(conn, en_root, ru_root, name="test") -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, en_root, ru_root) VALUES (?, ?, ?)",
        (name, str(en_root), str(ru_root)),
    )
    conn.commit()
    return cur.lastrowid


def get_unit(conn, key):
    return conn.execute("SELECT * FROM units WHERE key = ?", (key,)).fetchone()


EN = 'l_english:\n greet:0 "Hello"\n bye:0 "Goodbye"\n'
RU = 'l_russian:\n greet:0 "Привет"\n bye:0 "Goodbye" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'


def test_path_mapping_middle_suffix():
    """The language mark happens to be mid-name too: agot_modifiers_l_english_BLA.yml."""
    assert map_relpath("modifiers/agot_modifiers_l_english_BLA.yml",
                       "english", "russian") == \
        "modifiers/agot_modifiers_l_russian_BLA.yml"
    assert map_relpath("a_l_russian.yml", "russian", "english") == "a_l_english.yml"


def test_initial_import(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.new == 2
    assert get_unit(db, "greet")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "greet")["ru_text"] == "Привет"
    # the marker of the old scripts + ru==en -> not translated
    assert get_unit(db, "bye")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "bye")["ru_text"] is None


def test_empty_original_with_a_real_translation_stays_translated(db, make_tree):
    """An empty original goes to the ignored, but not over a live translation.

    The auto-ignore must not take a row into which a human has already written
    something: an empty value in the original is a reason not to torment the
    translator, not a reason to throw their work away.
    """
    en = make_tree({"mod_l_english.yml": 'l_english:\n k:0 ""\n other:0 "Text"\n'}, "en")
    ru = make_tree(
        {"mod_l_russian.yml": 'l_russian:\n k:0 "Живой перевод"\n other:0 "Текст"\n'}, "ru")
    scan_project(db, make_project(db, en, ru))
    assert get_unit(db, "k")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "k")["ru_text"] == "Живой перевод"


def test_empty_original_without_a_translation_is_ignored_at_once(db, make_tree):
    """The very first scan puts a stub into «ignored» and not among the untranslated."""
    en = make_tree({"mod_l_english.yml": 'l_english:\n k:0 ""\n other:0 "Text"\n'}, "en")
    stats = scan_project(db, make_project(db, en, make_tree({}, "ru")))
    assert stats.auto_ignored == 1
    assert get_unit(db, "k")["status"] == Status.IGNORED.value
    assert get_unit(db, "other")["status"] == Status.UNTRANSLATED.value


def test_original_that_went_empty_keeps_the_ignore(db, make_tree, tmp_path):
    """The text in the original is gone — the row stays ignored, not «stale»."""
    en = make_tree({"mod_l_english.yml": 'l_english:\n k:0 "[GetName]"\n'}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    scan_project(db, pid)
    assert get_unit(db, "k")["status"] == Status.IGNORED.value

    (en / "mod_l_english.yml").write_text(
        'l_english:\n k:0 ""\n', encoding="utf-8-sig", newline="\n")
    scan_project(db, pid)
    assert get_unit(db, "k")["status"] == Status.IGNORED.value


def test_rescan_unchanged(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    stats = scan_project(db, pid)
    assert stats.new == 0 and stats.unchanged == 2 and stats.stale == 0


def test_en_modified_translated_becomes_stale(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello there"\n bye:0 "Goodbye"\n'}, "en")
    stats = scan_project(db, pid)
    u = get_unit(db, "greet")
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "Hello"
    assert u["en_text"] == "Hello there"
    assert u["ru_text"] == "Привет"          # the translation is kept
    assert stats.stale == 1


def test_en_modified_again_keeps_prev(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello v2"\n bye:0 "Goodbye"\n'}, "en")
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello v3"\n bye:0 "Goodbye"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "greet")
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "Hello"      # NOT overwritten with v2
    assert u["en_text"] == "Hello v3"


def test_en_modified_untranslated_stays(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello"\n bye:0 "Farewell"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "bye")
    assert u["status"] == Status.UNTRANSLATED.value
    assert u["en_text"] == "Farewell"
    assert u["prev_en_text"] is None


def test_key_deleted_and_restored(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n bye:0 "Goodbye"\n'}, "en")
    stats = scan_project(db, pid)
    assert stats.deleted == 1
    assert get_unit(db, "greet")["is_deleted"] == 1
    make_tree({"mod_l_english.yml": EN}, "en")
    stats = scan_project(db, pid)
    assert stats.restored == 1
    u = get_unit(db, "greet")
    assert u["is_deleted"] == 0
    assert u["ru_text"] == "Привет"          # the translation survived the deletion


def test_key_without_source_goes_to_archive(db, make_tree):
    """The key is in the translation but not in the original: the translation to the archive, no row."""
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree(
        {"mod_l_russian.yml": RU.rstrip() + '\n old_key:0 "Старьё"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 1
    assert get_unit(db, "old_key") is None
    row = db.execute(
        "SELECT * FROM legacy_translations WHERE key = 'old_key'").fetchone()
    assert row["ru_text"] == "Старьё"


def test_translation_file_without_source_archived(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({
        "mod_l_russian.yml": RU,
        "extra_l_russian.yml": 'l_russian:\n lonely:0 "Одинокий"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 1
    assert stats.orphan_ru_files == ["extra_l_russian.yml"]
    assert db.execute(
        "SELECT ru_text FROM legacy_translations WHERE key='lonely'").fetchone()[0] == "Одинокий"
    # a file without a pair we do not set up in the project
    assert db.execute(
        "SELECT COUNT(*) FROM files WHERE rel_path = 'extra_l_russian.yml'").fetchone()[0] == 0


def test_deleted_key_translation_archived(db, make_tree):
    """The key vanished from the original at an update of the mod — the translation is kept."""
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n bye:0 "Goodbye"\n'}, "en")
    make_tree({"mod_l_russian.yml": 'l_russian:\n bye:0 "Пока"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.deleted == 1
    assert db.execute(
        "SELECT ru_text FROM legacy_translations WHERE key='greet'").fetchone()[0] == "Привет"


def test_updated_junk_files_ignored(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({
        "mod_l_russian.yml": RU,
        "mod_l_russian_updated.yml": 'l_russian:\n greet:0 "Мусор"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 0
    assert get_unit(db, "greet")["ru_text"] == "Привет"


def test_tm_auto_fill_same_text(db, make_tree):
    # two keys with the same EN: one is translated -> the second is filled from the TM as auto
    en = make_tree({"mod_l_english.yml":
                    'l_english:\n a:0 "Same text"\n b:0 "Same text"\n'}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Одинаковый"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.auto_filled == 1
    u = get_unit(db, "b")
    assert u["status"] == Status.AUTO.value
    assert u["ru_text"] == "Одинаковый"


def test_tm_fills_ambiguous_with_the_same_winner_as_f7(db, make_tree):
    """A divergence of variants no longer silences the substitution.

    With two different translations of one original the auto-fill used to keep
    quiet, while F7 in the same situation substitutes the best variant with
    confidence. The databases diverge in the translation of one row constantly,
    and the silence cost percentage points of filling for nothing. Now both paths
    pick one and the same winner.
    """
    from pdxloc.core import tm

    en = make_tree({
        "m1_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Same"\n c:0 "Same"\n',
    }, "en")
    ru = make_tree({
        "m1_l_russian.yml": 'l_russian:\n a:0 "Вариант1"\n b:0 "Вариант2"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)

    assert stats.auto_filled == 1
    unit = get_unit(db, "c")
    assert unit["status"] == Status.AUTO.value      # «substituted, check it»
    assert unit["ru_text"] == tm.lookup(db, "Same")[0].ru_text


def test_en_modified_auto_reset(db, make_tree):
    en = make_tree({"mod_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Same"\n'}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Один"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.AUTO.value
    # the EN of key b changed -> auto is reset, and there is no new match in the TM
    make_tree({"mod_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Different now"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "b")
    assert u["status"] == Status.UNTRANSLATED.value
    assert u["ru_text"] is None


def test_ru_conflict_db_wins(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    # on the disk the translation was changed, in the DB there is one of our own -> the DB rules
    make_tree({"mod_l_russian.yml": 'l_russian:\n greet:0 "Другой перевод"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.ru_conflicts == 1
    assert get_unit(db, "greet")["ru_text"] == "Привет"


def test_duplicate_key_last_wins(db, make_tree):
    en = make_tree({"mod_l_english.yml":
                    'l_english:\n dup:0 "First"\n dup:0 "Second"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert len(stats.duplicate_keys) == 1
    assert get_unit(db, "dup")["en_text"] == "Second"


def test_untranslated_ru_appears_on_disk(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    # the user translated bye right in the file
    make_tree({"mod_l_russian.yml":
               'l_russian:\n greet:0 "Привет"\n bye:0 "Пока"\n'}, "ru")
    scan_project(db, pid)
    u = get_unit(db, "bye")
    assert u["status"] == Status.TRANSLATED.value
    assert u["ru_text"] == "Пока"

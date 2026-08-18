"""Канарейки на критический путь: завести проект → скан → перевод → запись.

Повод конкретный. Сопоставление EN- и RU-файлов молча перестало работать для
самой обычной раскладки модов мастерской, и приложение показало проект на
138 тысяч строк с нулём переводов — при том, что готовый перевод лежал рядом на
диске. Ни один тест не упал: все проверяли частности, и ни один не спрашивал
главного — «а перевод-то нашёлся?».

Здесь проверяется именно это, на всех раскладках, которые встречаются живьём.
Тесты нарочно грубые: они не про детали, а про то, что инструмент вообще
выполняет свою работу.
"""
from __future__ import annotations

import pytest

from pdxloc import project
from pdxloc.core import tm
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

EN = (
    'l_english:\n'
    ' greet:0 "Hello"\n'
    ' bye:0 "Goodbye"\n'
    ' again:0 "Hello"\n'          # повтор — им проверяем автоподстановку
)
RU = (
    'l_russian:\n'
    ' greet:0 "Привет"\n'
    ' bye:0 "Пока"\n'
)


def write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)


def layout_flat(root):
    """Корни указаны прямо на папки языка."""
    write(root / "en" / "agot" / "foo_l_english.yml", EN)
    write(root / "ru" / "agot" / "foo_l_russian.yml", RU)
    return root / "en", root / "ru"


def layout_workshop(root):
    """Как в мастерской: два мода, корень — папка localization."""
    write(root / "2962333032" / "localization" / "english" / "agot" / "foo_l_english.yml", EN)
    write(root / "2962803371" / "localization" / "russian" / "agot" / "foo_l_russian.yml", RU)
    return (root / "2962333032" / "localization",
            root / "2962803371" / "localization")


def layout_same_tree(root):
    """Оригинал и перевод в одном моде: localization/<язык>/…"""
    write(root / "mod" / "localization" / "english" / "foo_l_english.yml", EN)
    write(root / "mod" / "localization" / "russian" / "foo_l_russian.yml", RU)
    return root / "mod" / "localization", root / "mod" / "localization"


def layout_deep(root):
    """Папка языка не первым сегментом пути."""
    write(root / "en" / "sub" / "english" / "foo_l_english.yml", EN)
    write(root / "ru" / "sub" / "russian" / "foo_l_russian.yml", RU)
    return root / "en", root / "ru"


LAYOUTS = {
    "папки языка": layout_flat,
    "мастерская: два мода": layout_workshop,
    "один мод": layout_same_tree,
    "язык в глубине пути": layout_deep,
}


@pytest.fixture(params=list(LAYOUTS), ids=list(LAYOUTS))
def scanned(request, tmp_path):
    en_root, ru_root = LAYOUTS[request.param](tmp_path)
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en_root, tgt_root=ru_root)
    stats = scan_project(conn, 1)
    yield conn, stats
    conn.close()


def test_existing_translation_is_never_lost(scanned) -> None:
    """Главная канарейка: перевод лежит на диске — он обязан найтись.

    Ноль переведённых при непустом дереве перевода означает, что сломано
    сопоставление файлов, и работать с таким проектом нельзя.
    """
    conn, _ = scanned
    translated = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL AND ru_text <> ''"
    ).fetchone()[0]
    assert translated > 0, "перевод есть на диске, но проект его не увидел"


def test_translations_land_on_the_right_keys(scanned) -> None:
    conn, _ = scanned
    rows = dict(conn.execute(
        "SELECT key, ru_text FROM units WHERE ru_text IS NOT NULL").fetchall())
    assert rows["greet"] == "Привет"
    assert rows["bye"] == "Пока"


def test_paired_files_are_not_treated_as_orphans(scanned) -> None:
    """Осиротевший RU-файл уходит в архив — так терялся весь перевод сразу."""
    conn, stats = scanned
    assert stats.files_ru >= stats.files_en
    assert conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == 0


def test_memory_is_filled_from_the_translation(scanned) -> None:
    """Пустая память переводов = молчащие подсказки и автоподстановка."""
    conn, _ = scanned
    assert [h.ru_text for h in tm.lookup(conn, "Hello")] == ["Привет"]


def test_repeated_string_is_autofilled(scanned) -> None:
    """Точное совпадение с уже переведённой строкой подставляется само."""
    conn, _ = scanned
    row = conn.execute(
        "SELECT status, ru_text FROM units WHERE key = 'again'").fetchone()
    assert row["ru_text"] == "Привет"
    assert row["status"] == Status.AUTO.value      # «подставлено, проверь»


def test_nothing_is_left_untranslated_when_everything_matches(scanned) -> None:
    conn, _ = scanned
    left = conn.execute(
        "SELECT COUNT(*) FROM units WHERE status = ?",
        (Status.UNTRANSLATED.value,)).fetchone()[0]
    assert left == 0


def test_export_writes_the_translation_back(scanned, tmp_path) -> None:
    """Замыкаем круг: то, что прочитали, должно записаться обратно в мод."""
    conn, _ = scanned
    out = tmp_path / "out_mod"
    export_project(conn, 1, ExportOptions(), out_root=out, backup=False)
    written = list(out.rglob("*_l_russian.yml"))
    assert written, "запись перевода в мод не создала ни одного файла"
    text = written[0].read_text(encoding="utf-8-sig")
    assert "Привет" in text and "Пока" in text


def test_rescan_is_idempotent(scanned) -> None:
    """Повторный скан не должен ни терять переводы, ни плодить архив."""
    conn, _ = scanned
    before = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    scan_project(conn, 1)
    after = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    assert after == before
    assert conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == 0

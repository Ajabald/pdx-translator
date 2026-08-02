"""QA-проверки перевода: сохранность CK3-токенов, длина, спецпоследовательности.

Сравнение токенов — мультимножества (Counter): важно и наличие, и количество.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter

from ck3loc.core.models import Issue
from ck3loc.core.statuses import Status

RE_BRACKET = re.compile(r"\[[^\[\]]*\]")            # [GetTrait('x').GetName], [men_at_arms|E]
RE_DOLLAR = re.compile(r"\$[A-Za-z0-9_.|=+\-]+\$")  # $VALUE$, $VALUE|=+0$
RE_ICON = re.compile(r"£[A-Za-z0-9_]+£")            # £gold£
RE_FMT_OPEN = re.compile(r"#(?!!)[A-Za-z][A-Za-z_;]*")  # #bold, #weak, #high;italic
RE_FMT_CLOSE = re.compile(r"#!")
RE_NEWLINE = re.compile(r"\\n")

# (severity, русское сообщение)
#
# Главный принцип: сравниваем перевод С ОРИГИНАЛОМ, а не с абстрактной нормой.
# Прежняя проверка «в переводе число #тегов должно равняться числу #!» давала
# 826 ложных срабатываний из 827 на живом проекте: в CK3 тег #weak в конце
# строки закрывать не обязательно, и «несбалансирован» сам оригинал мода.
CODES: dict[str, tuple[str, str]] = {
    "dollar_mismatch": ("error", "Переменные $…$ не совпадают с оригиналом"),
    "icon_mismatch": ("error", "Иконки £…£ не совпадают с оригиналом"),
    "fmt_mismatch": ("error", "Набор тегов оформления отличается от оригинала"),
    "fmt_broken": ("error", "В оригинале теги закрыты, в переводе — нет"),
    "empty_translated": ("error", "Статус «переведено», но перевод пуст"),
    "brackets_mismatch": ("warning", "Скриптовые ссылки [ ] отличаются от оригинала"),
    "newline_mismatch": ("warning", "Число переносов \\n отличается от оригинала"),
    "same_as_en": ("warning", "Перевод совпадает с оригиналом"),
    "inconsistent": ("warning", "Такой же оригинал переведён в проекте иначе"),
    "edge_space": ("warning", "Лишние пробелы в начале или в конце"),
    "double_space": ("warning", "Двойные пробелы в переводе"),
    "unbalanced_quotes": ("warning", "Непарные кавычки или скобки в переводе"),
    "len_ratio": ("warning", "Подозрительная длина перевода"),
}

# Проверки, выключенные по умолчанию: шумят больше, чем помогают.
# len_ratio — эвристика старого скрипта, давала 208 срабатываний (4% строк).
OPTIONAL_CODES = frozenset({"len_ratio"})

# Проверки, которым нужен весь проект, а не одна строка
PROJECT_WIDE_CODES = frozenset({"inconsistent"})

_PAIRS = (("«", "»"), ("(", ")"), ("[", "]"), ("{", "}"))


def strip_markup(text: str) -> str:
    """Убрать CK3-разметку для сравнения длины (перенос из старого check_translation)."""
    text = RE_BRACKET.sub("", text)
    text = RE_DOLLAR.sub("", text)
    text = RE_ICON.sub("", text)
    text = RE_FMT_OPEN.sub("", text)
    text = RE_FMT_CLOSE.sub("", text)
    text = text.replace("\\n", " ")
    return text.strip()


def _multiset(pattern: re.Pattern, text: str) -> Counter:
    return Counter(pattern.findall(text))


def _unbalanced_pairs(text: str) -> bool:
    """Непарные кавычки или скобки — частый след обрезанного перевода."""
    for left, right in _PAIRS:
        if text.count(left) != text.count(right):
            return True
    return text.count('"') % 2 == 1


def check_unit(
    en_text: str,
    ru_text: str,
    *,
    enabled: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Коды проблем для пары «оригинал — перевод».

    По умолчанию работают все правила, кроме шумных из OPTIONAL_CODES.
    """
    active = enabled if enabled is not None else set(CODES) - OPTIONAL_CODES
    codes: list[str] = []

    def add(code: str) -> None:
        if code in active:
            codes.append(code)

    if not ru_text.strip():
        return ["empty_translated"] if "empty_translated" in active else []

    if _multiset(RE_DOLLAR, en_text) != _multiset(RE_DOLLAR, ru_text):
        add("dollar_mismatch")
    if _multiset(RE_ICON, en_text) != _multiset(RE_ICON, ru_text):
        add("icon_mismatch")

    # Теги оформления сверяем с оригиналом: сколько их было, столько и должно
    # остаться. Отдельно ловим случай, когда оригинал закрыт, а перевод — нет.
    if _multiset(RE_FMT_OPEN, en_text) != _multiset(RE_FMT_OPEN, ru_text):
        add("fmt_mismatch")
    en_opens = len(RE_FMT_OPEN.findall(en_text))
    en_closes = len(RE_FMT_CLOSE.findall(en_text))
    ru_opens = len(RE_FMT_OPEN.findall(ru_text))
    ru_closes = len(RE_FMT_CLOSE.findall(ru_text))
    if en_opens == en_closes and ru_opens != ru_closes:
        add("fmt_broken")

    if _multiset(RE_BRACKET, en_text) != _multiset(RE_BRACKET, ru_text):
        add("brackets_mismatch")
    if len(RE_NEWLINE.findall(en_text)) != len(RE_NEWLINE.findall(ru_text)):
        add("newline_mismatch")

    if ru_text == en_text:
        add("same_as_en")
    if ru_text != ru_text.strip():
        add("edge_space")
    if "  " in ru_text.replace("\\n", " ").strip():
        add("double_space")
    if _unbalanced_pairs(ru_text):
        add("unbalanced_quotes")

    if "len_ratio" in active and ru_text != en_text:
        en_clean, ru_clean = strip_markup(en_text), strip_markup(ru_text)
        if len(en_clean) >= 10 and ru_clean:
            ratio = len(ru_clean) / len(en_clean)
            if ratio < 0.5 or ratio > 2.0:
                codes.append("len_ratio")

    return codes


def find_inconsistent(conn: sqlite3.Connection, project_id: int) -> dict[int, str]:
    """Строки, где одинаковый оригинал переведён по-разному.

    Возвращает {unit_id: подсказка с вариантами} — проверка на весь проект,
    поэтому её нельзя выполнить, глядя на одну строку.
    """
    rows = conn.execute(
        """SELECT u.id, u.en_hash, u.ru_text FROM units u
           JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0
             AND u.ru_text IS NOT NULL AND u.en_hash IS NOT NULL
             AND u.status IN (?, ?, ?)""",
        (project_id, Status.TRANSLATED.value, Status.REVIEWED.value, Status.CUSTOM.value),
    ).fetchall()

    by_hash: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_hash.setdefault(row["en_hash"], []).append(row)

    result: dict[int, str] = {}
    for group in by_hash.values():
        variants = {r["ru_text"] for r in group}
        if len(variants) > 1:
            hint = " · ".join(sorted(v[:60] for v in variants))
            for row in group:
                result[row["id"]] = hint
    return result


def ignored_pairs(conn: sqlite3.Connection) -> set[tuple[int, str]]:
    """Что пользователь пометил как «это не ошибка»."""
    try:
        return {(r["unit_id"], r["code"]) for r in conn.execute(
            "SELECT unit_id, code FROM qa_ignores")}
    except sqlite3.Error:      # таблицы ещё нет (старая схема)
        return set()


def ignore_issue(conn: sqlite3.Connection, unit_id: int, code: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO qa_ignores (unit_id, code) VALUES (?, ?)", (unit_id, code))
    conn.commit()


def unignore_issue(conn: sqlite3.Connection, unit_id: int, code: str) -> None:
    conn.execute("DELETE FROM qa_ignores WHERE unit_id = ? AND code = ?", (unit_id, code))
    conn.commit()


def check_unit_in_project(
    conn: sqlite3.Connection, unit_id: int, *, enabled=None) -> list[str]:
    """Проверки для одной строки — то, что пересчитывается при сохранении."""
    row = conn.execute(
        "SELECT id, en_text, ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or row["en_text"] is None or row["ru_text"] is None:
        return []
    codes = check_unit(row["en_text"], row["ru_text"], enabled=enabled)
    ignored = {code for uid, code in ignored_pairs(conn) if uid == unit_id}
    return [c for c in codes if c not in ignored]


def run_qa(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    only_translated: bool = True,
    enabled: frozenset[str] | set[str] | None = None,
) -> list[Issue]:
    statuses = (
        (Status.TRANSLATED.value, Status.REVIEWED.value, Status.AUTO.value,
         Status.STALE.value, Status.CUSTOM.value)
        if only_translated
        else tuple(s.value for s in Status if s != Status.IGNORED)
    )
    rows = conn.execute(
        f"""SELECT u.id, u.key, u.en_text, u.ru_text, f.rel_path
            FROM units u JOIN files f ON f.id = u.file_id
            WHERE f.project_id = ? AND u.is_deleted = 0
              AND u.en_text IS NOT NULL AND u.ru_text IS NOT NULL
              AND u.status IN ({','.join('?' * len(statuses))})""",
        (project_id, *statuses),
    ).fetchall()

    active = enabled if enabled is not None else set(CODES) - OPTIONAL_CODES
    ignored = ignored_pairs(conn)
    inconsistent = (
        find_inconsistent(conn, project_id) if "inconsistent" in active else {})

    issues: list[Issue] = []
    for r in rows:
        codes = check_unit(r["en_text"], r["ru_text"], enabled=active)
        if r["id"] in inconsistent:
            codes.append("inconsistent")
        for code in codes:
            if (r["id"], code) in ignored:
                continue
            severity, message = CODES[code]
            if code == "inconsistent":
                message = f"{message}: {inconsistent[r['id']]}"
            issues.append(Issue(
                unit_id=r["id"], key=r["key"], file_rel_path=r["rel_path"],
                code=code, severity=severity, message=message,
            ))
    issues.sort(key=lambda i: (i.severity != "error", i.file_rel_path, i.key))
    return issues

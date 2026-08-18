"""QA-проверки перевода: сохранность CK3-токенов, длина, спецпоследовательности.

Сравнение токенов — мультимножества (Counter): важно и наличие, и количество.

**Замечания кешируются в самой строке** (`units.qa_hash`, `units.qa_codes`).
Повод — замер: полный проход по проекту ванильной HOI4 (124 893 пары) занимает
3,35 с, и раньше он шёл при каждом открытии проекта, в потоке интерфейса.
Кеш живёт в строке, а не в отдельной таблице, ровно затем, чтобы его нельзя
было забыть сбросить: `qa_hash` считается от набора правил и обоих текстов
сразу, поэтому любая правка перевода, приход новой редакции оригинала или смена
набора правил обесценивают его сами собой. Пометки «это не ошибка»
(`qa_ignores`) в кеш не входят — они накладываются поверх, и менять их можно
не пересчитывая ничего.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence

from pdxloc.core import markup, qa_rules
from pdxloc.core.models import Issue
from pdxloc.core.statuses import Status

# Описание самих токенов живёт в core/markup.py — там же сказано, кто их
# использует. Здесь оставлены имена: по ним ходят проверки ниже и тесты.
RE_BRACKET = markup.pattern("bracket")
RE_DOLLAR = markup.pattern("dollar")
RE_ICON = markup.pattern("icon_pound")
RE_ICON_AT = markup.pattern("icon_at")
RE_FMT_OPEN = markup.pattern("fmt_open")
RE_FMT_CLOSE = markup.pattern("fmt_close")
RE_NEWLINE = markup.pattern("newline")
RE_ESCAPE_SEQ = qa_rules.RE_ESCAPE_SEQ

# (severity, русское сообщение) — производная от встроенного набора правил.
# По ней ходят окно отчёта и колонка «!» таблицы.
CODES: dict[str, tuple[str, str]] = qa_rules.default_ruleset().codes()

# Правила, выключенные по умолчанию. Осталось именем ради старого кода:
# состояние живёт в самом правиле (Rule.enabled).
OPTIONAL_CODES = frozenset(
    r.id for r in qa_rules.BUILTIN_RULES if not r.enabled)


def strip_markup(text: str) -> str:
    """Убрать разметку для сравнения длины. Реализация — в core/markup.py."""
    return markup.strip_markup(text)


def check_unit(
    en_text: str,
    ru_text: str,
    *,
    enabled: frozenset[str] | set[str] | None = None,
    ruleset: qa_rules.RuleSet | None = None,
) -> list[str]:
    """Коды проблем для пары «оригинал — перевод».

    Сами проверки живут в `core/qa_rules.py` — вместе с параметрами, которыми
    их настраивают. Здесь остался вход: `enabled` ограничивает набор кодов (так
    зовут старый код и тесты), `ruleset` подставляет настроенный набор целиком.
    """
    rules = ruleset if ruleset is not None else qa_rules.default_ruleset()
    if enabled is not None:
        rules = rules.restricted_to(enabled)
    return rules.check(en_text, ru_text)


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


# --- кеш замечаний -------------------------------------------------------

def ruleset_fingerprint(rules: qa_rules.RuleSet) -> str:
    """Отпечаток набора правил — всё, от чего зависят коды замечаний.

    Серьёзность сюда не входит намеренно: она красит колонку «!», но не меняет
    ни одного кода, а пересчитывать сотню тысяч строк из-за смены цвета было бы
    обидно.
    """
    payload = json.dumps(
        [[r.id, r.enabled, r.params] for r in rules],
        sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def pair_hash(fingerprint: str, en_text: str, ru_text: str) -> str:
    """Отпечаток проверенной пары. Сошёлся — замечания в строке ещё годны."""
    raw = f"{fingerprint}\x1f{en_text}\x1f{ru_text}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _codes_of(stored: str | None) -> list[str]:
    return stored.split(",") if stored else []


def _remember(conn: sqlite3.Connection, checked: Sequence[tuple[str, str, int]]) -> None:
    """Записать посчитанное. Ошибка записи гасится: кеш — ускоритель.

    Соединение бывает и только на чтение (фоновые замеры открывают именно
    такое), и остаться без таблицы строк из-за этого нельзя.
    """
    if not checked:
        return
    try:
        conn.executemany(
            "UPDATE units SET qa_hash = ?, qa_codes = ? WHERE id = ?", checked)
        conn.commit()
    except sqlite3.Error:
        pass


def cached_issues(
    conn: sqlite3.Connection,
    rows: Iterable[sqlite3.Row],
    rules: qa_rules.RuleSet,
) -> dict[int, list[str]]:
    """Коды замечаний строк: из кеша, где он годен, иначе пересчётом.

    `rows` — уже выбранные строки; нужны поля `id`, `en_text`, `ru_text` и,
    чтобы кеш вообще работал, `qa_hash` с `qa_codes`. Без них (запрос старого
    вида) всё считается заново — медленно, но верно.
    """
    rows = list(rows)
    fingerprint = ruleset_fingerprint(rules)
    cached = bool(rows) and {"qa_hash", "qa_codes"} <= set(rows[0].keys())

    issues: dict[int, list[str]] = {}
    checked: list[tuple[str, str, int]] = []
    for row in rows:
        en_text, ru_text = row["en_text"], row["ru_text"]
        if not en_text or not ru_text:
            continue
        wanted = pair_hash(fingerprint, en_text, ru_text)
        if cached and row["qa_hash"] == wanted:
            codes = _codes_of(row["qa_codes"])
        else:
            codes = rules.check(en_text, ru_text)
            checked.append((wanted, ",".join(codes), row["id"]))
        if codes:
            issues[row["id"]] = codes
    if cached:
        _remember(conn, checked)
    return issues


def recheck_one(
    conn: sqlite3.Connection,
    unit_id: int,
    rules: qa_rules.RuleSet,
) -> list[str]:
    """Пересчитать замечания одной строки и обновить её кеш."""
    row = conn.execute(
        "SELECT id, en_text, ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or not row["en_text"] or not row["ru_text"]:
        return []
    codes = rules.check(row["en_text"], row["ru_text"])
    _remember(conn, [(pair_hash(ruleset_fingerprint(rules),
                                row["en_text"], row["ru_text"]),
                      ",".join(codes), unit_id)])
    return codes


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


def run_qa(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    only_translated: bool = True,
    enabled: frozenset[str] | set[str] | None = None,
    ruleset: qa_rules.RuleSet | None = None,
) -> list[Issue]:
    # машинный перевод здесь обязателен: потерянная подстановка или сломанный
    # тултип — самое частое, что он приносит, и увидеть это надо до записи в мод
    statuses = (
        (Status.TRANSLATED.value, Status.REVIEWED.value, Status.AUTO.value,
         Status.MACHINE.value, Status.STALE.value, Status.CUSTOM.value)
        if only_translated
        else tuple(s.value for s in Status if s != Status.IGNORED)
    )
    rows = conn.execute(
        f"""SELECT u.id, u.key, u.en_text, u.ru_text, f.rel_path,
                   u.qa_hash, u.qa_codes
            FROM units u JOIN files f ON f.id = u.file_id
            WHERE f.project_id = ? AND u.is_deleted = 0
              AND u.en_text IS NOT NULL AND u.ru_text IS NOT NULL
              AND u.status IN ({','.join('?' * len(statuses))})""",
        (project_id, *statuses),
    ).fetchall()

    rules = ruleset if ruleset is not None else qa_rules.default_ruleset()
    if enabled is not None:
        rules = rules.restricted_to(enabled)
    active = rules.active_ids()

    ignored = ignored_pairs(conn)
    inconsistent = (
        find_inconsistent(conn, project_id) if "inconsistent" in active else {})

    # тот же кеш, что питает колонку «!»: отчёт по проекту, открытый сразу
    # после таблицы, не должен считать всё заново
    found = cached_issues(conn, rows, rules)

    issues: list[Issue] = []
    for r in rows:
        codes = list(found.get(r["id"], ()))
        if r["id"] in inconsistent:
            codes.append("inconsistent")
        for code in codes:
            if (r["id"], code) in ignored:
                continue
            message = rules.message(code)
            if code == "inconsistent":
                message = f"{message}: {inconsistent[r['id']]}"
            issues.append(Issue(
                unit_id=r["id"], key=r["key"], file_rel_path=r["rel_path"],
                code=code, severity=rules.severity(code), message=message,
            ))
    # Ошибки выше предупреждений, предупреждения — выше сигналов
    issues.sort(key=lambda i: (qa_rules.SEVERITY_RANK.get(i.severity, 9),
                               i.file_rel_path, i.key))
    return issues

"""Quality checks: CK3 tokens kept intact, length, special sequences.

Tokens are compared as multisets (Counter): both presence and count matter.

**Issues are cached in the row itself** (`units.qa_hash`, `units.qa_codes`). The
reason is a measurement: a full pass over the vanilla HOI4 project (124 893
pairs) takes 3.35 s, and it used to run on every project open, on the interface
thread. The cache lives in the row rather than in a table of its own precisely so
that it cannot be forgotten and left stale: `qa_hash` is computed from the rule
set and both texts at once, so any edit to the translation, any new revision of
the original and any change of rule set invalidate it by themselves. The «not an
error» marks (`qa_ignores`) are not part of the cache — they are laid on top, and
changing them recomputes nothing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence

from pdxloc.core import markup, qa_rules
from pdxloc.core.models import Issue
from pdxloc.core.statuses import Status

# The tokens themselves are described in core/markup.py, together with who uses
# them. What is left here are the names: the checks below and the tests go by
# them.
RE_BRACKET = markup.pattern("bracket")
RE_DOLLAR = markup.pattern("dollar")
RE_ICON = markup.pattern("icon_pound")
RE_ICON_AT = markup.pattern("icon_at")
RE_FMT_OPEN = markup.pattern("fmt_open")
RE_FMT_CLOSE = markup.pattern("fmt_close")
RE_NEWLINE = markup.pattern("newline")
RE_ESCAPE_SEQ = qa_rules.RE_ESCAPE_SEQ

# (severity, message) — derived from the built-in rule set. The report window
# and the «!» column of the table both go by it.
CODES: dict[str, tuple[str, str]] = qa_rules.default_ruleset().codes()

# Rules that are off by default. The name is kept for the sake of older code:
# the state lives in the rule itself (Rule.enabled).
OPTIONAL_CODES = frozenset(
    r.id for r in qa_rules.BUILTIN_RULES if not r.enabled)


def strip_markup(text: str) -> str:
    """Strip the markup for a length comparison. The implementation is in
    core/markup.py."""
    return markup.strip_markup(text)


def check_unit(
    en_text: str,
    ru_text: str,
    *,
    enabled: frozenset[str] | set[str] | None = None,
    ruleset: qa_rules.RuleSet | None = None,
) -> list[str]:
    """The issue codes for one «original — translation» pair.

    The checks themselves live in `core/qa_rules.py`, together with the
    parameters that tune them. What is left here is the way in: `enabled` narrows
    the set of codes — that is how the older code and the tests call it — while
    `ruleset` substitutes a configured set whole.
    """
    rules = ruleset if ruleset is not None else qa_rules.default_ruleset()
    if enabled is not None:
        rules = rules.restricted_to(enabled)
    return rules.check(en_text, ru_text)


def find_inconsistent(conn: sqlite3.Connection, project_id: int) -> dict[int, str]:
    """Rows where one and the same original is translated differently.

    Returns {unit_id: a hint listing the variants}. It is a whole-project check,
    so it cannot be answered by looking at a single row.
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


# --- the issue cache ---

def ruleset_fingerprint(rules: qa_rules.RuleSet) -> str:
    """A fingerprint of the rule set: everything the issue codes depend on.

    The severity is deliberately left out: it colours the «!» column but changes
    not a single code, and recomputing a hundred thousand rows over a change of
    colour would be a shame.
    """
    payload = json.dumps(
        [[r.id, r.enabled, r.params] for r in rules],
        sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def pair_hash(fingerprint: str, en_text: str, ru_text: str) -> str:
    """A fingerprint of a checked pair. If it matches, the row's issues still hold."""
    raw = f"{fingerprint}\x1f{en_text}\x1f{ru_text}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _codes_of(stored: str | None) -> list[str]:
    return stored.split(",") if stored else []


def _remember(conn: sqlite3.Connection, checked: Sequence[tuple[str, str, int]]) -> None:
    """Store what was computed. A write error is swallowed: the cache is only a
    speed-up.

    The connection is sometimes read-only — the background counters open exactly
    such a one — and losing the row table over that is not acceptable.
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
    """Issue codes for rows: from the cache where it holds, by recomputing where
    it does not.

    `rows` are already selected rows; the fields `id`, `en_text`, `ru_text` are
    needed, and `qa_hash` with `qa_codes` for the cache to work at all. Without
    them — an older shape of query — everything is computed afresh: slow, but
    correct.
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
    """Recompute the issues of one row and refresh its cache."""
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
    """What the user has marked as «not an error»."""
    try:
        return {(r["unit_id"], r["code"]) for r in conn.execute(
            "SELECT unit_id, code FROM qa_ignores")}
    except sqlite3.Error:      # the table does not exist yet (an older schema)
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
    # machine translation is mandatory here: a lost substitution or a broken
    # tooltip is the commonest thing it brings, and that has to be seen before it
    # is written to the mod
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

    # the same cache that feeds the «!» column: a project report opened right after
    # the table must not compute everything again
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
    # Errors above warnings, warnings above signals
    issues.sort(key=lambda i: (qa_rules.SEVERITY_RANK.get(i.severity, 9),
                               i.file_rel_path, i.key))
    return issues

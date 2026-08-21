"""Project statistics in one place — one definition of «translated» for every screen.

done = translated + reviewed + (custom with a non-empty ru_text).
total does NOT include orphaned and ignored rows: they stay out of the
denominator of the percentage.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from pdxloc.core.i18n import fill, translate
from pdxloc.core.statuses import Status

DONE_SQL = ("(u.status IN ('translated','reviewed') "
            "OR (u.status = 'custom' AND u.ru_text IS NOT NULL))")

_EXCLUDED_FROM_TOTAL = (Status.IGNORED.value,)


@dataclass
class ProjectStats:
    total: int = 0
    done: int = 0
    counts: dict[str, int] = field(default_factory=dict)   # per status

    @property
    def remaining(self) -> int:
        return self.total - self.done

    @property
    def pct(self) -> float:
        return round(100 * self.done / self.total, 1) if self.total else 0.0


@dataclass
class FileStats:
    rel_path: str
    total: int = 0
    done: int = 0
    counts: dict[str, int] = field(default_factory=dict)


def project_stats(conn: sqlite3.Connection, project_id: int) -> ProjectStats:
    stats = ProjectStats()
    rows = conn.execute(
        f"""SELECT u.status, COUNT(*) AS n, SUM({DONE_SQL}) AS done
            FROM units u JOIN files f ON f.id = u.file_id
            WHERE f.project_id = ? AND u.is_deleted = 0
            GROUP BY u.status""",
        (project_id,),
    ).fetchall()
    for r in rows:
        stats.counts[r["status"]] = r["n"]
        if r["status"] not in _EXCLUDED_FROM_TOTAL:
            stats.total += r["n"]
            stats.done += r["done"] or 0
    return stats


def file_stats(conn: sqlite3.Connection, project_id: int) -> list[FileStats]:
    """Counters per file, for the tree on the left. Ordered by rel_path."""
    result: dict[str, FileStats] = {}
    rows = conn.execute(
        f"""SELECT f.rel_path, u.status, COUNT(*) AS n, SUM({DONE_SQL}) AS done
            FROM units u JOIN files f ON f.id = u.file_id
            WHERE f.project_id = ? AND u.is_deleted = 0 AND f.is_deleted = 0
            GROUP BY f.rel_path, u.status
            ORDER BY f.rel_path""",
        (project_id,),
    ).fetchall()
    for r in rows:
        fs = result.setdefault(r["rel_path"], FileStats(rel_path=r["rel_path"]))
        fs.counts[r["status"]] = r["n"]
        if r["status"] not in _EXCLUDED_FROM_TOTAL:
            fs.total += r["n"]
            fs.done += r["done"] or 0
    return list(result.values())


def format_status_bar(stats: ProjectStats) -> str:
    msg = fill(translate("Stats", "Translated %1 / %2 (%3%) · left %4"),
               stats.done, stats.total, stats.pct, stats.remaining)
    if stats.counts.get(Status.MACHINE.value):
        msg += fill(translate("Stats", " · machine: %1"),
                    stats.counts[Status.MACHINE.value])
    if stats.counts.get(Status.AUTO.value):
        msg += fill(translate("Stats", " · auto: %1"),
                    stats.counts[Status.AUTO.value])
    if stats.counts.get(Status.STALE.value):
        msg += fill(translate("Stats", " · outdated: %1"),
                    stats.counts[Status.STALE.value])
    return msg

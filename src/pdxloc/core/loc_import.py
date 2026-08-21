"""Loading a translation from a ready localisation tree, as its own command.

In ESP/ESM Translator this is `Translation → Load translation from a translated
mod`, with a rules window of its own. Here a translation used to be pulled in
only inside a scan and only into empty rows: if a key already had a translation,
the version on disk was silently ignored — the scanner merely counted it as a
divergence. So there was no way to take somebody else's translation of a mod, or
one's own edits made in the files.

**The work is split into three steps, and that is not decoration.**

    read_tree   — the disk only: parse the translation files
    build_plan  — the comparison only: what changes into what
    apply_plan  — the write only: one transaction for the whole batch

All of it used to be one pass, and the window called it three or four times per
import: a preview when it opened, a preview on every checkbox, one more for the
number in «take N rows?», and only then for real. Meanwhile **the checkboxes do
not affect the parsing** — they change the selection rules, while the files read
are the same ones. Now the tree is parsed once, and toggling a checkbox
recomputes only the comparison, in memory.

The write goes as a batch rather than row by row, and that is the second half of
the same story. Measured over 20 000 rows: row by row 16.7 s, as a batch 0.53 s —
a thirty-two-fold difference. The cause is not the SQL but a `commit` per row: the
database lives in WAL with `synchronous=FULL`, so every row cost one fsync. The
side effect matters no less: a batch is either applied whole or not applied at
all, whereas the old path left half the rows written when it failed halfway.

The batch path keeps the history and the status transitions by the same means as a
manual edit: `unit_ops.record_history` and `unit_ops.status_after_edit`.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats, tm, unit_ops
from pdxloc.core.models import LocEntry
from pdxloc.core.scanner import LEGACY_MARKER

ProgressCb = Callable[[int, int, str], None]


class ImportCancelled(Exception):
    """Reading was interrupted by the user; nothing reached the database."""


@dataclass
class ImportOptions:
    """The rules for taking rows, the same as in EET's Import window."""

    overwrite: bool = False              # overwrite existing translations
    skip_equal_to_source: bool = True    # skip rows where the translation equals the original
    only_files: set[str] | None = None   # limit to a set of original rel_paths


@dataclass
class ImportReport:
    files_found: int = 0
    imported: int = 0
    unchanged: int = 0              # the disk holds the same as the project
    skipped_existing: int = 0       # a translation is already there and overwriting is off
    skipped_equal: int = 0          # the translation equals the original
    skipped_marked: int = 0         # marked with the «needs translation» marker
    unknown_keys: int = 0           # the project has no such keys: another mod, or an old one
    warnings: list[str] = field(default_factory=list)
    samples: list[tuple[str, str, str]] = field(default_factory=list)  # key, before, after

    SAMPLE_LIMIT = 200

    def summary(self) -> str:
        """The outcome of loading a translation from the mod files."""
        lines = [
            fill(translate("LocImport", "Translation files found: %1"),
                 self.files_found),
            fill(translate("LocImport", "Rows taken: %1"), self.imported),
        ]
        if self.unchanged:
            lines.append(fill(translate("LocImport", "Already the same: %1"),
                              self.unchanged))
        if self.skipped_existing:
            lines.append(fill(translate(
                "LocImport", "Skipped (a translation already exists): %1"),
                self.skipped_existing))
        if self.skipped_equal:
            lines.append(fill(translate(
                "LocImport", "Skipped (translation equals the original): %1"),
                self.skipped_equal))
        if self.skipped_marked:
            lines.append(fill(translate(
                "LocImport", "Skipped (the «needs translation» marker): %1"),
                self.skipped_marked))
        if self.unknown_keys:
            lines.append(fill(translate("LocImport", "Keys absent from the project: %1"),
                 self.unknown_keys))
        return "\n".join(lines)


@dataclass(frozen=True)
class ParsedTree:
    """The parsed translation tree: what was read from disk.

    It lives in the import window until the folder changes: the import rules do
    not alter it.
    """

    tgt_dir: Path
    files: dict[str, dict[str, LocEntry]]      # rel_path of the original -> {key: entry}
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Change:
    """One row the import will take."""

    unit_id: int
    key: str
    en_text: str | None
    old_text: str | None
    new_text: str          # already brought into the Paradox form
    status: str
    prev_en_text: str | None
    change_kind: str | None


@dataclass
class ImportPlan:
    """What the import will do. Nothing is written, so it can be shown and thought
    better of."""

    changes: list[Change] = field(default_factory=list)
    report: ImportReport = field(default_factory=ImportReport)


def read_tree(
    tgt_dir: Path,
    rel_paths: list[str],
    src_lang: str,
    tgt_lang: str,
    *,
    fmt: loc_formats.LocFormat | None = None,
    encoding: str = "",
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ParsedTree:
    """Parse the translation files. Reading only; the database takes no part.

    `rel_paths` are the paths of the **original** files: the names of the
    translation files follow from them by substituting the language, and there is
    no reason to take anything from disk beyond what the project has.
    """
    tgt_dir = Path(tgt_dir)
    fmt = fmt or loc_formats.get(loc_formats.DEFAULT)
    if not tgt_dir.is_dir():
        raise FileNotFoundError(fill(translate(
            "LocImport", "Translation folder not found: %1"), tgt_dir))

    files: dict[str, dict[str, LocEntry]] = {}
    warnings: list[str] = []
    for i, rel in enumerate(rel_paths):
        if should_cancel is not None and should_cancel():
            raise ImportCancelled
        if progress_cb:
            progress_cb(i, len(rel_paths), rel)
        path = tgt_dir / fmt.map_relpath(rel, src_lang, tgt_lang)
        if not path.is_file():
            continue
        lf = fmt.parse_file(path, language=tgt_lang, encoding=encoding)
        warnings.extend(lf.warnings)
        # the last one wins, as in the game
        files[rel] = {e.key: e for e in lf.entries}

    if progress_cb:
        progress_cb(len(rel_paths), len(rel_paths), "done")
    return ParsedTree(tgt_dir=tgt_dir, files=files, warnings=warnings)


def build_plan(
    conn: sqlite3.Connection,
    project_id: int,
    tree: ParsedTree,
    options: ImportOptions | None = None,
    *,
    fmt: loc_formats.LocFormat | None = None,
) -> ImportPlan:
    """Compare the parsed tree with the project. Writes nothing and never touches
    the disk."""
    fmt = fmt or loc_formats.get(loc_formats.DEFAULT)
    options = options or ImportOptions()
    plan = ImportPlan()
    report = plan.report
    report.warnings.extend(tree.warnings)

    # One query per project instead of a query per file: rows run to hundreds of
    # thousands and files to hundreds, and hundreds of extra trips to the database
    # serve nothing here.
    units_by_file: dict[int, dict[str, sqlite3.Row]] = {}
    for row in conn.execute(
        """SELECT u.id, u.key, u.file_id, u.en_text, u.ru_text, u.status,
                  u.prev_en_text, u.change_kind
           FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0""",
        (project_id,),
    ):
        units_by_file.setdefault(row["file_id"], {})[row["key"]] = row

    files = conn.execute(
        "SELECT id, rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
        "ORDER BY rel_path", (project_id,)).fetchall()

    for f in files:
        rel = f["rel_path"]
        if options.only_files is not None and rel not in options.only_files:
            continue
        entries = tree.files.get(rel)
        if entries is None:
            continue
        report.files_found += 1
        units = units_by_file.get(f["id"], {})
        report.unknown_keys += sum(1 for k in entries if k not in units)

        for key, entry in entries.items():
            unit = units.get(key)
            if unit is None or not entry.text:
                continue
            if LEGACY_MARKER in entry.comment_inline:
                report.skipped_marked += 1
                continue
            if options.skip_equal_to_source and entry.text == (unit["en_text"] or ""):
                report.skipped_equal += 1
                continue
            current = unit["ru_text"] or ""
            if entry.text == current:
                report.unchanged += 1
                continue
            if current and not options.overwrite:
                report.skipped_existing += 1
                continue

            # The text is brought into the Paradox form right here rather than at write
            # time: the plan is shown to a person, and what is shown must be what actually
            # lands in the database.
            new_text = fmt.escape_value(entry.text)
            status, prev_en, change_kind = unit_ops.status_after_edit(
                unit["status"], new_text, unit["ru_text"],
                unit["prev_en_text"], unit["change_kind"])
            plan.changes.append(Change(
                unit_id=unit["id"], key=key, en_text=unit["en_text"],
                old_text=unit["ru_text"], new_text=new_text,
                status=status, prev_en_text=prev_en, change_kind=change_kind))
            report.imported += 1
            if len(report.samples) < ImportReport.SAMPLE_LIMIT:
                report.samples.append((key, current, entry.text))

    return plan


def apply_plan(
    conn: sqlite3.Connection,
    plan: ImportPlan,
    *,
    batch_id: str | None = None,
) -> ImportReport:
    """Write the plan in a single transaction.

    Either all of it is applied or none: the old path committed every row on its
    own, and a failure halfway left half of it taken — with no way to tell which
    half.
    """
    changes = plan.changes
    if not changes:
        return plan.report

    try:
        unit_ops.record_history(conn, [c.unit_id for c in changes],
                                origin="import", batch_id=batch_id)
        conn.executemany(
            "UPDATE units SET ru_text = ?, status = ?, prev_en_text = ?, "
            "change_kind = ?, updated_at = datetime('now') WHERE id = ?",
            [(c.new_text, c.status, c.prev_en_text, c.change_kind, c.unit_id)
             for c in changes],
        )
        # What is taken feeds the translation memory, as a manual edit does: the
        # translation of somebody else's mod is valuable precisely because it will
        # prompt you in your own.
        tm.upsert_many(conn, [(c.en_text, c.new_text, c.key) for c in changes
                              if c.en_text and c.new_text])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    # a batch can run to tens of thousands of rows, so the journal is flushed at
    # once, as after a scan (see project.checkpoint)
    from pdxloc.project import checkpoint

    checkpoint(conn)
    return plan.report


def import_translations(
    conn: sqlite3.Connection,
    project_id: int,
    tgt_dir: Path,
    options: ImportOptions | None = None,
    *,
    dry_run: bool = False,
    batch_id: str | None = None,
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ImportReport:
    """Take the translations from the `tgt_dir` tree — all three steps at once.

    `dry_run` computes the same thing but writes nothing: a mass operation with
    no «here is exactly what will change» is dangerous.
    """
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(fill(translate("LocImport", "Project id=%1 not found"), project_id))
    from pdxloc.project import languages as project_languages

    langs = project_languages(conn, project_id)
    rel_paths = [r["rel_path"] for r in conn.execute(
        "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
        "ORDER BY rel_path", (project_id,))]
    from pdxloc.project import get_loc_encoding, get_loc_format

    fmt = loc_formats.get(get_loc_format(conn) or loc_formats.DEFAULT)
    tree = read_tree(tgt_dir, rel_paths, langs.src_lang, langs.tgt_lang,
                     fmt=fmt, encoding=get_loc_encoding(conn) or "",
                     progress_cb=progress_cb, should_cancel=should_cancel)
    plan = build_plan(conn, project_id, tree, options, fmt=fmt)
    if dry_run:
        return plan.report
    return apply_plan(conn, plan, batch_id=batch_id)

"""Writing the translation tree out in the game format.

BOM, the `l_<language>:` header, and the order of the original file.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from pdxloc import settings
from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats
from pdxloc.core.models import ExportOptions, ExportReport, LocEntry
from pdxloc.core.scanner import LEGACY_MARKER
from pdxloc.core.statuses import Status

# What counts as fit to write into the mod. `Status.MACHINE` is deliberately
# left out: nobody has read machine translation. It is added only under an
# explicit checkbox — see `ExportOptions.include_machine`.
TRANSLATED_STATUSES = (
    Status.TRANSLATED.value, Status.REVIEWED.value,
    Status.AUTO.value, Status.STALE.value, Status.CUSTOM.value,
)


def _safe_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "project"


# A snapshot is named after the time of the write; that is exactly the form
# `write_translation` below creates. The cleanup needs the pattern: without it
# any subfolder counts as a snapshot, and `rmtree` does not ask.
SNAPSHOT_NAME = "%Y-%m-%d_%H%M%S"
_SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")


def _prune_backups(project_dir: Path, keep: int | None = None) -> None:
    """Keep only the last snapshots: a backup insures a write, it does not keep a
    history.

    How many exactly is asked at call time rather than taken from a default
    argument: that would be computed once at import, and a change of the setting
    would have no effect until a restart.

    **Other people's folders are left alone.** Any subfolder used to count as a
    snapshot, and a folder somebody had put into `backups/<project>/` by hand went
    into `rmtree` together with the old snapshots — silently and without
    confirmation. A snapshot has a strict name of its own (`SNAPSHOT_NAME`), so it
    can be told from a stranger for certain; whatever does not match the pattern
    is not ours, and we have no right to delete it.
    """
    if keep is None:
        keep = settings.backup_keep()
    snapshots = sorted(p for p in project_dir.iterdir()
                       if p.is_dir() and _SNAPSHOT_RE.match(p.name))
    for old in snapshots[:-keep] if keep > 0 else snapshots:
        shutil.rmtree(old, ignore_errors=True)


def _attach_raw(entries: list[LocEntry], fmt, target: Path,
                target_read: tuple[str, str], source: Path,
                source_read: tuple[str, str]) -> None:
    """Give the entries their source lines back, matched by key.

    In two passes: first from the original tree, then from the file being
    overwritten — that one is newer and must win. An entry found in neither is
    left without `raw`, and the format writes it from its own template: it is a
    new key, and its other columns have nowhere to come from.

    Each tree is read in **its own** encoding: in the older format the original
    lies in cp1252 and the translation in cp1251, and one encoding for both would
    corrupt somebody else's columns in silence — a corrupted line encodes back
    without raising anything at all.
    """
    raw: dict[str, str] = {}
    for path, (language, encoding) in ((source, source_read),
                                       (target, target_read)):
        if not path.is_file():
            continue
        try:
            loc = fmt.parse_file(path, language=language, encoding=encoding)
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        raw.update({e.key: e.raw for e in loc.entries if e.raw})
    for entry in entries:
        entry.raw = raw.get(entry.key, "")


def _write_atomically(target: Path, text: str, encoding: str = "utf-8-sig") -> None:
    """Write a mod file so that it cannot be left truncated.

    `open(target, "w")` empties the file at once, before the first byte: let the
    process die halfway and a stub is left in the localisation folder, and **the
    game reads it as the real thing**. We write next to it and swap in one move:
    `os.replace` is atomic on Windows, so either the whole previous file is
    visible or the new one.

    The neighbouring `.tmp` is invisible to the game — it reads only localisation
    files — and an interrupted export leaves it as litter which the next write
    overwrites.

    `fsync` is deliberately not called: it guards against a sudden power cut, but
    costs a great deal, and one export can touch hundreds of files. Against a
    crash of the application — the case that actually happens — the swap guards
    just as well.

    Line endings: LF in the current format of the series, which is what the game
    itself writes, and CRLF in the older one, as in all of its files; otherwise
    editing one row would show the whole file as changed in a diff.
    """
    tmp = target.with_name(target.name + ".tmp")
    newline = "\n" if encoding.startswith("utf") else "\r\n"
    with open(tmp, "w", encoding=encoding, newline=newline,
              errors="replace") as fh:
        fh.write(text)
    os.replace(tmp, target)


def export_project(
    conn: sqlite3.Connection,
    project_id: int,
    options: ExportOptions,
    *,
    out_root: Path | None = None,
    backup: bool = True,
    backup_root: Path | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> ExportReport:
    """Write the translation files. `out_root` defaults to the project's ru_root.

    A project may have no translation folder at all — one for a mod that is
    English only is created without it — and then `out_root` is obligatory.

    Previous versions of the overwritten files go into a tree of their own
    (`settings.backups_dir()`): they must not be kept next to the localisation —
    the game reads every `*.yml` from that folder and would load a copy on equal
    terms with the original.
    """
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(fill(translate("Exporter", "Project id=%1 not found"), project_id))
    from pdxloc.project import translation_root_of

    root = Path(out_root) if out_root is not None else translation_root_of(proj["ru_root"])
    if root is None:
        # A project of a mod that has no translation yet is created without a
        # folder to write into. Refusing here is the whole point: writing to
        # wherever the application happens to be running would scatter the
        # translation over the disk and look like success.
        raise ValueError(translate(
            "Exporter", "The project has no translation folder: choose where to write."))
    from pdxloc.project import languages as project_languages

    langs = project_languages(conn, project_id)
    src_lang, tgt_lang = langs.src_lang, langs.tgt_lang

    from pdxloc.project import (get_loc_encoding, get_loc_format,
                                get_source_encoding)

    fmt = loc_formats.get(get_loc_format(conn) or loc_formats.DEFAULT)
    encoding = get_loc_encoding(conn) or fmt.encodings[0]
    src_encoding = get_source_encoding(conn) or encoding
    # A format with several encodings has to know it in advance: whether somebody
    # else's columns in a row survive the write depends on it (see
    # `paradox_csv.render`).
    render_options = {} if len(fmt.encodings) == 1 else {"encoding": encoding}

    files = conn.execute(
        "SELECT * FROM files WHERE project_id = ? AND is_deleted = 0 ORDER BY rel_path",
        (project_id,),
    ).fetchall()

    report = ExportReport()
    translated_statuses = set(TRANSLATED_STATUSES)
    if not options.include_stale:
        translated_statuses.discard(Status.STALE.value)
    if options.include_machine:
        translated_statuses.add(Status.MACHINE.value)

    snapshot: Path | None = None

    def backup_target(target: Path, ru_rel: str) -> None:
        """Put the previous version of a file aside. The folder is created only on the
    first copy."""
        nonlocal snapshot
        if snapshot is None:
            base = Path(backup_root) if backup_root is not None else settings.backups_dir()
            project_dir = base / _safe_name(proj["name"])
            project_dir.mkdir(parents=True, exist_ok=True)
            snapshot = project_dir / datetime.now().strftime(SNAPSHOT_NAME)
            snapshot.mkdir(exist_ok=True)
            report.backup_dir = str(snapshot)
        copy = snapshot / ru_rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, copy)

    for i, f in enumerate(files):
        if progress_cb:
            progress_cb(i, len(files), f["rel_path"])
        units = conn.execute(
            "SELECT * FROM units WHERE file_id = ? AND is_deleted = 0 ORDER BY line_no, key",
            (f["id"],),
        ).fetchall()

        entries: list[LocEntry] = []
        written = skipped = 0
        for u in units:
            has_ru = u["ru_text"] is not None and u["status"] in translated_statuses
            inline = ""
            if has_ru:
                text = u["ru_text"]
            elif options.mode == "all_fallback_en":
                text = u["en_text"] or ""
                report.keys_fallback_en += 1
                # mark what is untranslated: on the next scan the row is recognised as needing
                # translation again rather than as finished
                inline = f"# !!! {LEGACY_MARKER}"
            else:
                skipped += 1
                continue
            written += 1
            entries.append(LocEntry(
                key=u["key"],
                version=u["en_version"],
                text=text,
                comment_before=u["comment_before"],
                comment_inline=inline,
            ))

        report.keys_written += written
        report.keys_skipped += skipped
        ru_rel = fmt.map_relpath(f["rel_path"], src_lang, tgt_lang)
        report.per_file.append((ru_rel, written, skipped))
        if not entries:
            continue

        target = root / ru_rel
        if not fmt.language_in_path:
            # The format of the older games: next to the translation a row also holds the
            # French, German and Spanish columns, the `x` marker and a trailing comment.
            # The database has none of them — it stores only the «original → translation»
            # pair — so the source lines are taken from disk: first from the file being
            # overwritten, and from the original tree when there is none.
            _attach_raw(entries, fmt, target, (tgt_lang, encoding),
                        Path(proj["en_root"]) / f["rel_path"],
                        (src_lang, src_encoding))

        trailing = f["trailing"] if "trailing" in f.keys() else ""
        text = fmt.render(tgt_lang, entries, trailing, **render_options)
        # leave the file alone when the content has not changed: the modification dates
        # are kept and mod managers are not made to rebuild the package
        if target.is_file():
            try:
                if target.read_text(encoding=encoding) == text:
                    report.files_unchanged += 1
                    continue
            except (OSError, UnicodeDecodeError):
                pass
            if backup:
                backup_target(target, ru_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(target, text, encoding)
        report.files_written += 1

    if snapshot is not None:
        _prune_backups(snapshot.parent)
    if progress_cb:
        progress_cb(len(files), len(files), "done")
    return report

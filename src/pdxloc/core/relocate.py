"""Changing the original folder of an existing project.

`en_root` was set when the project was created and edited nowhere else, while the
folder is not forever: the mod was downloaded from Nexus again somewhere else,
the Steam library moved to another drive, the project was handed to another
person. The only way out used to be editing the path by hand in SQLite.

The danger of the operation is that file paths in the database are relative: a
file the new folder does not have turns deleted on the next scan, and its
translations move to the archive. So this module only counts the matches — the
window shows them before the button is pressed, and a separate call writes the
path.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core.paradox_yaml import lang_tag
from pdxloc.core import loc_formats
from pdxloc.core.tm_import import language_dirs

# How deep the language folder is looked for inside the chosen one: the path to
# localization/replace/english is three levels.
MAX_DEPTH = 3


@dataclass
class RootPreview:
    """What happens if the chosen folder becomes the original folder."""

    chosen: Path                      # what the user chose
    root: Path | None = None          # what will be written (sometimes a subfolder of chosen)
    matched: list[str] = field(default_factory=list)   # database files found in the folder
    missing: list[str] = field(default_factory=list)   # database files that are not there
    added: list[str] = field(default_factory=list)     # folder files the database does not know
    units_missing: int = 0            # rows in the files that went missing
    translated_missing: int = 0       # of those, the translated ones: they move to the archive
    known_files: int = 0              # how many original files the database knows
    candidates: list[tuple[Path, int]] = field(default_factory=list)
    error: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this path can be written."""
        return self.error is None and self.root is not None

    @property
    def risky(self) -> bool:
        """Not the whole set matched: worth asking again before writing."""
        return bool(self.missing)

    def summary(self) -> str:
        """What happens to the project rows if the folder is changed."""
        if self.error:
            return self.error
        lines = [fill(translate("Relocate", "Folder: %1"), self.root)]
        if self.root is not None and Path(self.root) != Path(self.chosen):
            lines.append(fill(translate(
                "Relocate", "%1 was chosen, but the localization files lie in "
                            "%2 — that is what will be recorded."),
                self.chosen, self.root))
        lines.append(
            fill(translate("Relocate",
                           "Files matched: %1 out of the %2 the database knows."),
                 len(self.matched), self.known_files))
        if self.missing:
            tail = (fill(translate(
                "Relocate",
                ", of them %1 with a translation will go to the archive."),
                self.translated_missing) if self.translated_missing else ".")
            lines.append(
                fill(translate("Relocate", "Files not found: %1 — %2"),
                     len(self.missing),
                     fill(translate("Relocate", "%1 rows will become deleted"),
                          self.units_missing))
                + tail)
            lines += [f"  {rel}" for rel in self.missing[:20]]
            if len(self.missing) > 20:
                lines.append(fill(translate("Relocate", "  … and %1 more"),
                                  len(self.missing) - 20))
        if self.added:
            lines.append(fill(translate(
                "Relocate",
                "New files: %1 — rows from them appear on the next scan."),
                len(self.added)))
            lines += [f"  {rel}" for rel in self.added[:20]]
            if len(self.added) > 20:
                lines.append(fill(translate("Relocate", "  … and %1 more"),
                                  len(self.added) - 20))
        if not self.matched:
            lines.append(translate(
                "Relocate",
                "Not a single database file was found in this folder. Looks "
                "like another mod's folder was chosen: after the change the "
                "whole translation goes to the archive."))
        elif not self.missing and not self.added:
            lines.append(translate(
                "Relocate",
                "The file set matches completely — the translation is safe."))
        lines.append("")
        lines.append(translate(
            "Relocate",
            "After the folder change a scan (F5) is needed: it re-reads the "
            "files and shows what changed in the original."))
        return "\n".join(lines)


def project_row(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise ValueError(fill(translate("Relocate", "Project id=%1 not found"), project_id))
    return row


def known_rel_paths(conn: sqlite3.Connection, project_id: int) -> list[str]:
    """The original files the database considers alive."""
    return [
        r["rel_path"] for r in conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
            "ORDER BY rel_path", (project_id,))
    ]


def _disk_rel_paths(root: Path, src_lang: str) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in loc_formats.get(loc_formats.detect(root)).files(root, src_lang)
    )


def _match(known: list[str], on_disk: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Match sets of paths case-insensitively: Windows does not tell case apart."""
    disk_by_lower = {rel.lower(): rel for rel in on_disk}
    matched, missing = [], []
    for rel in known:
        (matched if rel.lower() in disk_by_lower else missing).append(rel)
    known_lower = {rel.lower() for rel in known}
    added = [rel for rel in on_disk if rel.lower() not in known_lower]
    return matched, missing, added


def candidate_roots(chosen: Path, src_lang: str) -> list[Path]:
    """The chosen folder itself and every language folder inside it.

    People point sometimes at the whole mod folder, sometimes at localization,
    sometimes at the language folder proper. Choosing for them in silence is not
    allowed, so we return them all and the window explains why the one that was
    taken is not the one that was clicked.
    """
    chosen = Path(chosen)
    if not chosen.is_dir():
        return []
    roots: list[Path] = [chosen]
    seen = {chosen.resolve()}
    for path in language_dirs(chosen, src_lang, max_depth=MAX_DEPTH):
        if path.resolve() not in seen:
            seen.add(path.resolve())
            roots.append(path)
    return roots


def preview_root_change(
    conn: sqlite3.Connection, project_id: int, chosen: Path | str,
) -> RootPreview:
    """Work out the consequences of changing the original folder, changing nothing."""
    chosen = Path(str(chosen).strip())
    proj = project_row(conn, project_id)
    src_lang = proj["src_lang"] if "src_lang" in proj.keys() else "english"
    known = known_rel_paths(conn, project_id)
    preview = RootPreview(chosen=chosen, known_files=len(known))

    if not str(chosen) or not chosen.is_dir():
        preview.error = fill(
            translate("Relocate", "Folder not found: %1"), chosen)
        return preview

    # The best folder is the one where most of the files the database knows were
    # found. On a tie the first wins: the chosen folder itself, not a subfolder.
    scored: list[tuple[Path, int, list[str]]] = []
    for root in candidate_roots(chosen, src_lang):
        on_disk = _disk_rel_paths(root, src_lang)
        matched, _, _ = _match(known, on_disk)
        scored.append((root, len(matched), on_disk))
    preview.candidates = [(root, count) for root, count, _ in scored]

    best = max(scored, key=lambda item: item[1], default=None)
    if best is None or (best[1] == 0 and not any(item[2] for item in scored)):
        preview.error = fill(translate(
            "Relocate", "The folder has no localization files *%1*.yml:\n%2"),
            lang_tag(src_lang), chosen)
        return preview
    if best[1] == 0:
        # no familiar files, but localisation files are there: take the first folder
        # that holds any at all, and warn about it in the summary
        best = next(item for item in scored if item[2])

    root, _, on_disk = best
    preview.root = root
    preview.matched, preview.missing, preview.added = _match(known, on_disk)
    if preview.missing:
        marks = ",".join("?" * len(preview.missing))
        row = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COUNT(u.ru_text) AS translated
                  FROM units u JOIN files f ON f.id = u.file_id
                 WHERE f.project_id = ? AND u.is_deleted = 0
                       AND f.rel_path IN ({marks})""",
            (project_id, *preview.missing),
        ).fetchone()
        preview.units_missing = row["total"]
        preview.translated_missing = row["translated"]
    return preview


@dataclass
class LanguagePreview:
    """The consequences of changing a folder language, worked out before writing.

    Changing `src_lang` is more dangerous than it looks: the scanner finds files
    by the `_l_<language>` marker in the name, and after the change it will
    simply find none — every row turns deleted and the translations move to the
    archive. The same as a mistake in the path, only harder to notice: the folder
    is right where it was.
    """

    src_lang: str
    tgt_lang: str
    known_files: int = 0
    found: int = 0            # original files carrying the new language marker
    units_missing: int = 0
    translated_missing: int = 0
    scan_needed: bool = False       # what the scanner reads was changed

    @property
    def risky(self) -> bool:
        return self.scan_needed and self.found < self.known_files

    def summary(self) -> str:
        if not self.scan_needed:
            return translate(
                "Relocate",
                "Only the text language changes — files and rows are not "
                "affected. Machine translation, memory database naming and "
                "language-specific checks will use the new value.")
        lines = [fill(translate(
            "Relocate", "Files with the label _l_%1 in the original folder: "
                        "%2 of the %3 the database knows."),
            self.src_lang, self.found, self.known_files)]
        if self.found == 0:
            lines.append(translate(
                "Relocate",
                "Not a single file was found. After the change the scan will "
                "consider every row deleted and the translations will go to "
                "the archive."))
        elif self.found < self.known_files:
            lines.append(fill(translate(
                "Relocate",
                "%1 rows will become deleted, of them %2 with a translation."),
                self.units_missing, self.translated_missing))
        lines.append("")
        lines.append(translate(
            "Relocate",
            "After the change a scan (F5) is needed: it re-reads the files "
            "under the new names."))
        return "\n".join(lines)


def preview_language_change(
    conn: sqlite3.Connection,
    project_id: int,
    src_lang: str,
    tgt_lang: str,
) -> LanguagePreview:
    """Work out the consequences of changing the folder languages, changing nothing."""
    current = project_row(conn, project_id)
    known = known_rel_paths(conn, project_id)
    preview = LanguagePreview(src_lang=src_lang, tgt_lang=tgt_lang,
                              known_files=len(known))
    keys = current.keys()
    was_src = current["src_lang"] if "src_lang" in keys else "english"
    was_tgt = current["tgt_lang"] if "tgt_lang" in keys else "russian"
    preview.scan_needed = (src_lang != was_src) or (tgt_lang != was_tgt)
    if not preview.scan_needed:
        return preview

    root = Path(current["en_root"])
    if root.is_dir():
        on_disk = _disk_rel_paths(root, src_lang)
        matched, missing, _ = _match(known, on_disk)
        preview.found = len(matched)
        if missing:
            marks = ",".join("?" * len(missing))
            row = conn.execute(
                f"""SELECT COUNT(*) AS total, COUNT(u.ru_text) AS translated
                      FROM units u JOIN files f ON f.id = u.file_id
                     WHERE f.project_id = ? AND u.is_deleted = 0
                           AND f.rel_path IN ({marks})""",
                (project_id, *missing)).fetchone()
            preview.units_missing = row["total"]
            preview.translated_missing = row["translated"]
    return preview


# --- the translation folder ----------------------------------------------
#
# The same story as with the original folder, only worse: `ru_root` used to be
# written when the project was created and by nothing else at all, while it is
# the folder the translation is read from and written into.


@dataclass
class TargetPreview:
    """What the project gets if the chosen folder becomes the translation one."""

    chosen: Path
    paired: int = 0                   # project files that have a translation there
    known_files: int = 0              # original files the project knows
    exists: bool = False
    cleared: bool = False             # the path is empty: the project keeps no folder
    candidates: list[tuple[Path, int]] = field(default_factory=list)
    error: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this path can be written.

        An empty folder is not a mistake here — unlike the original folder, the
        translation one is often empty on purpose: it is where the write will
        put the files. An empty path is not a mistake either: it means the
        project keeps no translation folder at all. Only a path that cannot be a
        folder is refused.
        """
        return self.error is None

    def summary(self) -> str:
        """What the folder holds for this project."""
        if self.error:
            return self.error
        if self.cleared:
            return translate(
                "Relocate",
                "The project is left without a translation folder — it is asked "
                "for at the first write into the mod.")
        lines = [fill(translate("Relocate", "Folder: %1"), self.chosen)]
        if not self.exists:
            lines.append(translate(
                "Relocate",
                "The folder does not exist yet — it is created at the first write."))
        elif self.paired:
            lines.append(fill(translate(
                "Relocate", "Translation files found: %1 of %2"),
                self.paired, self.known_files))
        else:
            lines.append(fill(translate(
                "Relocate",
                "No translation files for this project here — the folder is "
                "where the write will put them. Files known: %1"), self.known_files))
        return "\n".join(lines)


def preview_target_change(
    conn: sqlite3.Connection, project_id: int, chosen: Path | str,
) -> TargetPreview:
    """Work out what the chosen translation folder holds, changing nothing."""
    from pdxloc.project import get_loc_format

    # The text is checked before it becomes a path: `Path("")` is the current
    # directory, and an empty field here means «no folder», not «this one».
    text = str(chosen).strip()
    chosen = Path(text)
    proj = project_row(conn, project_id)
    src_lang = proj["src_lang"] if "src_lang" in proj.keys() else "english"
    tgt_lang = proj["tgt_lang"] if "tgt_lang" in proj.keys() else "russian"
    known = known_rel_paths(conn, project_id)
    preview = TargetPreview(chosen=chosen, known_files=len(known))

    if not text:
        preview.cleared = True
        return preview
    if chosen.exists() and not chosen.is_dir():
        preview.error = fill(
            translate("Relocate", "This is a file, not a folder: %1"), chosen)
        return preview

    preview.exists = chosen.is_dir()
    fmt = loc_formats.get(get_loc_format(conn) or loc_formats.DEFAULT)
    if preview.exists:
        preview.paired = sum(
            1 for rel in known
            if (chosen / fmt.map_relpath(rel, src_lang, tgt_lang)).is_file())
        preview.candidates = [(chosen, preview.paired)]
    return preview


def get_en_root(conn: sqlite3.Connection, project_id: int) -> Path:
    return Path(project_row(conn, project_id)["en_root"])


def set_en_root(conn: sqlite3.Connection, project_id: int, root: Path | str) -> Path:
    """Write the new original folder. The rows are left alone: the scan sorts them out."""
    root = Path(root)
    conn.execute(
        "UPDATE projects SET en_root = ? WHERE id = ?", (str(root), project_id))
    conn.commit()
    return root


def get_ru_root(conn: sqlite3.Connection, project_id: int) -> Path | None:
    """The translation folder; `None` when the project has none yet."""
    from pdxloc.project import translation_root_of

    return translation_root_of(project_row(conn, project_id)["ru_root"])


def set_ru_root(conn: sqlite3.Connection, project_id: int,
                root: Path | str | None) -> Path | None:
    """Write the new translation folder. `None` clears it back to «not chosen».

    Nothing is moved and nothing is rewritten: the folder decides where the next
    scan reads the translation from and where the write puts it.
    """
    from pdxloc.project import set_translation_root

    set_translation_root(conn, root, project_id)
    return Path(root) if root is not None and str(root).strip() else None

"""Shared dataclass models of the core, with no Qt in sight."""
from __future__ import annotations

from dataclasses import dataclass, field

from pdxloc.core.i18n import fill, translate


@dataclass
class LocEntry:
    """One entry of a localisation file.

    `text` is the raw text between the quotes, with escapes left unexpanded.
    """
    key: str
    version: str          # the digits after ':', '' when there are none
    text: str
    comment_before: str = ""   # raw lines (comments, blanks) above the entry, newlines included
    comment_inline: str = ""   # '# …' after the closing quote, '' when absent
    line_no: int = 0           # the ordinal of the entry in the file, 0..n-1
    # The source line of the file in full — needed by formats that write by
    # replacing one piece rather than rebuilding the entry. In the CSV of the older
    # games the line also holds the French, German and Spanish columns, the `x`
    # marker and a trailing comment; rebuild the line and all of that would be lost.
    # For `.yml` the field stays empty: there an entry is rebuilt whole.
    raw: str = ""


@dataclass
class LocFile:
    language: str              # 'english' / 'russian' from the l_xxx: header
    entries: list[LocEntry] = field(default_factory=list)
    trailing: str = ""         # comments and blank lines after the last entry
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScanStats:
    files_en: int = 0
    files_ru: int = 0
    new: int = 0
    unchanged: int = 0
    stale: int = 0
    changed_cosmetic: int = 0     # a cosmetic edit: punctuation, case, whitespace
    changed_meaningful: int = 0   # the text or the markup changed
    deleted: int = 0
    restored: int = 0
    archived: int = 0            # translations of keys the original no longer has
    auto_filled: int = 0
    auto_ignored: int = 0
    ru_conflicts: int = 0
    duplicate_keys: list[str] = field(default_factory=list)      # 'file.yml: key'
    duplicate_keys_ru: list[str] = field(default_factory=list)   # the same for the translation tree
    empty_source_keys: list[str] = field(default_factory=list)   # an empty value in the original
    orphan_ru_files: list[str] = field(default_factory=list)     # translation files with no counterpart
    parse_warnings: list[str] = field(default_factory=list)
    # (file, key, translation in the database, translation on disk) — the database wins
    ru_conflict_list: list[tuple[str, str, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        """The scan summary as one block of text, for the results window and --scan-cli."""
        lines = [
            fill(translate("ScanStats", "EN files: %1, RU: %2"),
                 self.files_en, self.files_ru),
            fill(translate("ScanStats", "New keys: %1"), self.new),
            fill(translate("ScanStats", "Unchanged: %1"), self.unchanged),
            fill(translate("ScanStats",
                           "The original changed: %1 (meaningful %2, cosmetic %3)"),
                 self.stale, self.changed_meaningful, self.changed_cosmetic),
            fill(translate("ScanStats", "Deleted from EN: %1"), self.deleted),
            fill(translate("ScanStats", "Restored: %1"), self.restored),
            fill(translate("ScanStats",
                           "Moved to the archive (absent from the original): %1"),
                 self.archived),
            fill(translate("ScanStats", "Filled from translation memory: %1"),
                 self.auto_filled),
            fill(translate("ScanStats",
                           "Ignored automatically (nothing to translate): %1"),
                 self.auto_ignored),
            fill(translate("ScanStats", "RU conflicts (the database wins): %1"),
                 self.ru_conflicts),
        ]
        if self.duplicate_keys:
            lines.append(fill(translate("ScanStats", "Duplicate keys (original): %1"),
                              len(self.duplicate_keys)))
        if self.duplicate_keys_ru:
            lines.append(fill(translate("ScanStats", "Duplicate keys (translation): %1"),
                              len(self.duplicate_keys_ru)))
        if self.empty_source_keys:
            lines.append(fill(translate("ScanStats", "Keys with an empty original: %1"),
                              len(self.empty_source_keys)))
        if self.parse_warnings:
            lines.append(fill(translate("ScanStats", "Parser warnings: %1"),
                              len(self.parse_warnings)))
        return "\n".join(lines)


@dataclass
class TmHit:
    ru_text: str
    source: str                  # 'user' | 'import' | 'game' | 'project-export'
    origin: str | None           # where the variant came from: «Project» or a database name
    key: str | None
    uses: int
    updated_at: str
    id: int = 0                  # memory entry id; negative means it came from an attached database
    editable: bool = False       # editing is possible for the project's own memory only
    score: float = 1.0           # similarity of the original: 1.0 is an exact match
    en_text: str = ""            # the entry's original, shown when the match is not exact
    prio: int = 0                # source priority, as in tm_all


@dataclass
class Issue:
    unit_id: int
    key: str
    file_rel_path: str
    code: str
    severity: str              # 'error' | 'warning'
    message: str


@dataclass
class ExportOptions:
    mode: str = "translated_only"   # 'translated_only' | 'all_fallback_en'
    include_stale: bool = True
    # Machine translation does not reach the mod by default: nobody has read it,
    # and in the game it can lie about the meaning, break a tooltip or lose an
    # icon. Letting it out is a deliberate decision, not a default.
    include_machine: bool = False


@dataclass
class ExportReport:
    files_written: int = 0
    files_unchanged: int = 0
    keys_written: int = 0
    keys_skipped: int = 0
    keys_fallback_en: int = 0
    per_file: list[tuple[str, int, int]] = field(default_factory=list)  # (ru_rel_path, written, skipped)
    backup_dir: str | None = None   # where previous versions of the overwritten files were put

"""Paradox localisation formats: which parser to point at these files.

The series has two of them, and what divides them is not the game but the
generation of the engine:

| | `yml` | `csv` |
|---|---|---|
| games | CK3, HOI4, EU4, Stellaris, Victoria 3, Imperator, EU5 | CK2, EU3, Victoria 2, HoI3 |
| file | `mod_events_l_russian.yml` | `events.csv` |
| language | a folder and a marker in the file name | **a column inside the row** |
| encoding | UTF-8 with BOM | cp1251 / cp1252 |

**The format is decided by the data, not by the name of the game.** That is the
intent: the list of games in `core/games.py` is open — a game of your own is
created under a free-form name — and guessing by name would have to be redone
every time. Looking into the folder, on the other hand, is reliable: `l_english:`
on the first line of a `.yml` is unmistakable, and so is `#CODE;` in the header
of a `.csv`.

The answer is remembered in the project file (`project_meta.loc_format`) — not
for speed but for certainty: the original tree can leave with a drive, and then
the export must write in the format it read from rather than the one that can be
guessed from the remains.

The implementations live in `core/paradox_yaml.py` and `core/paradox_csv.py`;
here there is only the table of who can do what, and the choice.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from pdxloc.core import paradox_csv, paradox_yaml
from pdxloc.core.models import LocEntry, LocFile

YML = "yml"
CSV = "csv"


@dataclass(frozen=True, slots=True)
class LocFormat:
    """A format and the module that reads and writes it.

    We keep the **module** rather than eight references to its functions: that
    way a function replaced in the tests reaches the callers — a reference taken
    at import time never hears about `monkeypatch` — and it is obvious where to
    look for the implementation.
    """

    id: str
    ext: str
    impl: ModuleType
    # whether the language needs a folder of its own: in `csv` the language is a
    # column and the translation file is named like the original one, so the two
    # trees differ only by where they sit
    language_in_path: bool
    encodings: tuple[str, ...]

    # --- parsing and writing ---

    def parse_file(self, path: Path, *, language: str = "",
                   encoding: str = "") -> LocFile:
        return self.impl.parse_file(path, language=language, encoding=encoding)

    def render(self, language: str, entries: Iterable[LocEntry],
               trailing: str = "", **kwargs) -> str:
        return self.impl.render(language, entries, trailing, **kwargs)

    def write_file(self, path: Path, language: str, entries: Iterable[LocEntry],
                   trailing: str = "", **kwargs) -> None:
        self.impl.write_file(path, language, entries, trailing, **kwargs)

    def escape_value(self, text: str) -> str:
        return self.impl.escape_value(text)

    def unescape(self, text: str) -> str:
        return self.impl.unescape(text)

    # --- walking the tree ---

    def files(self, root: Path, language: str = "", *,
              skip_updated: bool = False) -> list[Path]:
        return self.impl.files(root, language, skip_updated=skip_updated)

    def map_relpath(self, rel_posix: str, from_lang: str, to_lang: str) -> str:
        return self.impl.map_relpath(rel_posix, from_lang, to_lang)

    def detect(self, root: Path) -> bool:
        return self.impl.detect(root)


FORMATS: dict[str, LocFormat] = {f.id: f for f in (
    LocFormat(id=YML, ext=".yml", impl=paradox_yaml,
              language_in_path=True, encodings=("utf-8-sig",)),
    LocFormat(id=CSV, ext=".csv", impl=paradox_csv,
              language_in_path=False, encodings=paradox_csv.ENCODINGS),
)}

# The order of asking: the current format of the series first. It is both the
# commoner one and the more strictly recognised — in `csv` the sign of an entry
# is weaker (a key, a separator and something after it), and only the content
# tells a data table from a localisation one.
ORDER: tuple[str, ...] = (YML, CSV)

DEFAULT = YML


def get(format_id: str) -> LocFormat:
    """A format by its id. An unfamiliar one gives the current format of the series.

    Unfamiliar is not an error: the value comes from a project file which may
    have been created by a version of the application that knew more formats.
    """
    return FORMATS.get(format_id, FORMATS[DEFAULT])


def detect(root: Path, *, default: str = DEFAULT) -> str:
    """The format of a tree by its content. An empty folder gives the default."""
    if not root.is_dir():
        return default
    for format_id in ORDER:
        if FORMATS[format_id].detect(root):
            return format_id
    return default


def entries_of(loc_file: LocFile) -> Iterable[LocEntry]:
    """The entries of a file, so the caller need not know the model fields."""
    return loc_file.entries


def normalize_newlines(text: str) -> str:
    """A line break in the form both formats share, for storing in the database.

    A real line break damages `.yml` and `.csv` alike: the entry is torn in two.
    So it is turned into the two-character form on save rather than on export —
    otherwise the database and the file differ by exactly that character, and the
    next scan reports an edit nobody made.

    The rest of the escaping is not shared between the formats (in `.csv` the
    semicolon is a separator as well) and is done when the file is written, in
    `render`.
    """
    return paradox_yaml.escape_value(text)

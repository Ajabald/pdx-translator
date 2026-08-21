"""The Paradox games: one localisation format, but different languages and pens.

Why a registry was needed. The `.yml` format with a BOM and an `l_<language>:`
header is the same across the series, so the application could translate mods for
Stellaris or HOI4 anyway. One thing was missing: **saying which game a project
belongs to**. Without it the memory databases of different games lie in one heap
and offer vanilla CK3 rows to a Victoria 3 translator, while the language lists
propose folders the game does not have.

The idea comes from ESP/ESM Translator, which has «Game selection» and a database
per game: a project and its databases live in the pen of their own game and do
not mix.

Each game has its own set of language folders, and that is not guesswork: it was
checked against `game_supported_languages.json` from ModTranslationHelper 1.4.3,
the only tool in this niche that had already gathered those lists.

**A game of your own** is created under a free-form name: the format is shared,
and there is no reason to forbid CK2, Victoria 2 or anything else. It gets the
common list of folders (`languages.PARADOX_LANGUAGES`) — the application has
nowhere to learn what languages somebody else's game understands.

Game names are **not translated**: they are product names, like the name of the
application itself (see «The interface language» in ARCHITECTURE.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from pdxloc.core.languages import PARADOX_LANGUAGES


@dataclass(frozen=True, slots=True)
class Game:
    id: str                      # stored in the project file and in the memory database
    title: str                   # shown to the person
    folder: str                  # the name of the pen on disk
    languages: tuple[str, ...]   # the localisation folders the game understands


CK3 = "ck3"

GAMES: dict[str, Game] = {g.id: g for g in (
    # The order matters: the first game is the one offered by default, and that is
    # still CK3, out of translating mods for which the application grew.
    Game("ck3", "Crusader Kings III", "CK3",
         ("english", "french", "german", "korean", "russian", "simp_chinese",
          "spanish")),
    # CK2 is the only game here from the older generation of the engine: its
    # localisation lies in CSV, where the language is a column rather than a folder
    # (see `core/paradox_csv.py`). Its format has no Russian at all — not one header
    # of a vanilla file says RUSSIAN — so it is absent from the list here too: a
    # translation into a language the game does not know is set by the project
    # locale, and it lands in the English column anyway.
    Game("ck2", "Crusader Kings II", "CK2",
         ("english", "french", "german", "spanish")),
    Game("eu4", "Europa Universalis IV", "EU4",
         ("english", "french", "german", "spanish")),
    # EU5 came out after ModTranslationHelper, so there is nothing to check its list
    # against and it gets the common set of folders of the series. A superfluous
    # folder in the list breaks nothing: the language box is editable and a person
    # simply will not pick a spare entry — while a missing one would force them to
    # type the language in by hand.
    Game("eu5", "Europa Universalis V", "EU5", tuple(PARADOX_LANGUAGES)),
    # Korean and Chinese were added not from the ModTranslationHelper list but from
    # the game itself: the `localisation/languages.yml` of an installed HOI4 has
    # them, and the folders for them sit next to the rest. The competitor's list was
    # gathered earlier and has fallen behind since — while a missing folder would
    # force people to type the language in by hand.
    Game("hoi4", "Hearts of Iron IV", "HOI4",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "russian", "simp_chinese", "spanish")),
    Game("stellaris", "Stellaris", "Stellaris",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "simp_chinese", "russian", "spanish")),
    Game("vic3", "Victoria 3", "Victoria 3",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "russian", "simp_chinese", "spanish", "turkish")),
    Game("imperator", "Imperator: Rome", "Imperator",
         ("english", "french", "german", "russian", "simp_chinese", "spanish")),
)}

ORDER: tuple[str, ...] = tuple(GAMES)


def slug(name: str) -> str:
    """The name of a game of your own → the id for the project file.

    Latin letters and no spaces: the value lands in the project file, in the
    memory database and in a folder name, and those three survive a change of
    keyboard layout and a move to another file system only in that form.
    """
    out = "".join(c if c.isalnum() and c.isascii() else "_" for c in name.lower())
    out = "_".join(part for part in out.split("_") if part)[:32]
    if not out or out in GAMES:
        # a «ck3 of your own» must not pretend to be the built-in one: that has a
        # language set of its own
        out = f"{out}_own" if out else "game"
    return out


def get(game_id: str, title: str = "") -> Game:
    """A game by its id. An unfamiliar one is a game of your own, with the common
    set of languages.

    An unfamiliar id is not an error: it comes from a project file, which may have
    been created by a newer version of the application or as a game of one's own.

    The pen of such a game is named **after its id** rather than after the name
    that was typed: the name is not stored in the project file, and there would be
    nothing left to recognise the `victoria_2` project by from a «Victoria 2»
    folder. The slug is built out of Latin letters precisely so it can serve as a
    folder name.
    """
    known = GAMES.get(game_id)
    if known is not None:
        return known
    return Game(game_id, title or game_id, game_id, tuple(PARADOX_LANGUAGES))


def title(game_id: str) -> str:
    return get(game_id).title


def languages(game_id: str) -> tuple[str, ...]:
    return get(game_id).languages


def folder(game_id: str) -> str:
    return get(game_id).folder


def by_folder(name: str) -> str | None:
    """The game id from a pen name. `None` means the folder is not a pen.

    The guard needs it: from the folder a project file lies in one has to tell
    whose pen it is — and stay silent when the folder is not about games at all.
    """
    for game in GAMES.values():
        if game.folder.casefold() == name.casefold():
            return game.id
    return None

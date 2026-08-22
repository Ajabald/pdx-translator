An offline desktop workbench for translating the localisation of Paradox game
mods — a string table with statuses, translation memory, a term glossary,
mod-version diffing and configurable markup checks.

What 0.1.2 adds and fixes is below; the description of 0.1.0 follows it, unchanged.

## ✨ New in 0.1.2

* **Rule presets are no longer tied to Russian.** A preset used to glue two
  unrelated things together — what the game's markup dictates and what a
  particular language does about grammar — which is why they were called
  «CK3 · Russian». They are now split. The preset is the game and nothing else:
  «Crusader Kings III», «Hearts of Iron IV», «Crusader Kings II», «Stellaris».
  The inflection helpers your language uses attach on their own, from the
  translation language of the project, and never appear in the list — they are
  not a choice, they are a property of the project.
* **Twelve pairs of game and language ship with their own helpers**, harvested
  from the games: French, German, Polish, Portuguese, Russian and Spanish across
  the four games. This is what the split was for. A French translator of a HOI4
  mod used to get 37 270 occurrences of their own inflection functions reported
  as lost references, because the only list in the box was the Russian one.
* **Settings from 0.1.0 and 0.1.1 keep working.** The old preset names are read
  as the new ones, so a project, a global configuration or a shared `.pdxqa`
  carries over untouched.
* **Rule and preset descriptions have been rewritten** for the person reading
  them, in each interface language rather than as a translation of one. The
  measurement counts they used to quote moved to the architecture notes, where
  they belong.
* **A project can be created without a translation folder.** A mod that exists
  only in English has no such folder, and the window used to demand one anyway.
  Leave the field empty and you are asked for the folder once, at the first
  write into the mod; after that it is remembered. The folder can also be
  changed at any time — «Project → Change translation folder…», with the same
  preview the original folder has had.

## 🔧 Fixed

* **Choosing the original folder no longer fills in the translation one.** It
  used to be guessed from the name of the neighbouring folder, so a mod keeping
  both languages in one tree — `…\mod\localization` with `english` and `russian`
  inside — got `…\mod\russian`, a folder the game never reads. Nothing failed:
  the project simply found no translation, and later offered to write into that
  same wrong place. The field is filled in by you now, and the grey hint in it
  says it may be left empty. And because the folder used to be written once and
  by nothing else, a project created with the wrong one stayed wrong for life;
  that is what the new command is for.

* **The first-run wizard could not build the first database.** «Build a
  database…» did nothing at all: the memory window wanted an open project, and
  on a fresh install there is none. The built application has no console, so
  the error had nowhere to go and the button simply looked dead. Without a
  project the window now opens on the one tab it was called for — building a
  database — and the wizard notices the database it has just built.
* **«Recommended» is no longer promised to everyone.** The word sat inside the
  name of the «CK3 · Russian» set, so a translator of HOI4 read a
  recommendation for somebody else's rules. The matching set is now chosen by
  the game and the translation language of the open project: it stands first in
  «Checks → Rule preset» and in the Shift+F6 window, and it carries the mark.
  With no project open nothing is recommended — naming a set at random is worse
  than saying nothing. What the checks actually do has not changed.
* **The wizard no longer contradicts itself about the language.** Its list
  stood on the language of the system while the window itself was drawn in the
  saved one, so an installation carrying settings over from the previous name
  of the application could greet you with Chinese headings above a list that
  said «Russian».
* **A README in Chinese**, next to the English and the Russian one — the
  interface has been translated for a while, the description had not.

## 🈶 About the Chinese interface

Everything is translated, but the windows that are new or rewritten in 0.1.2 —
the rules window, the rule descriptions, the glossary — were translated by
machine and have not been read by a native speaker. The wording is checked
against the terms the rest of the interface already uses, and nothing more than
that is claimed: in Qt Linguist those contexts are marked `unfinished`, which is
exactly what they are. Corrections are welcome.

## ✨ What it does

* **A project is a single file** (`*.pdxproj`) holding strings, translations,
  memory and archive. Put it anywhere, copy it, hand it to someone else.
* **Eight games of the series** — Crusader Kings III and II, Europa Universalis
  IV and V, Hearts of Iron IV, Stellaris, Victoria 3, Imperator: Rome — plus a
  custom game under any name. Each carries its own language folders, so you
  cannot pick a language that game does not have.
* **Translation memory** with attachable databases (`*.pdxtm`): the game's
  vanilla localisation, the translation of a parent mod, exports of other
  projects. Matches are filled in automatically.
* **Similar strings, not just exact matches.** When translating a submod there
  are almost no exact matches, but plenty of near ones — the panel shows them
  with a similarity score and the differences highlighted.
* **A glossary of terms.** Statistics over the memory proposes pairs like
  `Maester → мейстер`; you accept or reject, and a rejected one is not offered
  again. Accepted terms are highlighted in the original — hover shows the
  translation.
* **Machine translation** through six routes — DeepL, Claude, OpenAI, Google,
  Yandex, and manually through any web translator if you have no key. Markup is
  hidden from the service and put back afterwards; a batch is applied whole or
  not at all.
* **Mod updates.** After a rescan you see what the author changed, split into
  meaningful and cosmetic edits, with the changed words highlighted right in the
  source field. Cosmetic edits are confirmed in bulk, and any operation is
  undone with Ctrl+Z.
* **17 built-in quality checks you can tune**, plus your own rules in six kinds.
  The whole set travels to another translator as a single file.
* **Interface in English, Russian and Simplified Chinese**, switched on the fly.

## 📥 Download

**Windows 10/11, 64-bit** — no Python needed either way.

* [**pdx-translator-setup-0.1.2.exe**](https://github.com/Ajabald/pdx-translator/releases/download/v0.1.2/pdx-translator-setup-0.1.2.exe) — installer *(recommended)*
* [**pdx-translator-v0.1.2.zip**](https://github.com/Ajabald/pdx-translator/releases/download/v0.1.2/pdx-translator-v0.1.2.zip) — portable, 50 MB

The installer asks for no administrator rights and installs for the current
user. That is not laziness: the application keeps `Bdd`, `Projects` and
`backups` next to itself, and inside `Program Files` a normal user cannot write
there. Uninstalling leaves those folders alone — they hold your memory
databases, projects and backups of translations.

The portable archive is the same build: unpack it anywhere, run
`pdx-translator.exe`, and it can live on a flash drive.

From source (Python 3.11 or newer) — see the
[README](https://github.com/Ajabald/pdx-translator#installing-and-running).

## 📋 Worth knowing

* **Translation memory databases are not shipped.** That localisation belongs to
  Paradox and to the authors of the community translations, and distributing it
  is not ours to do. The tool builds a database from your own copy of the game
  in seconds — that is the first thing worth doing after installing.
* **The Chinese interface is beta.** It is proofread, but its terminology has
  not been checked against how Chinese Paradox modding communities actually name
  these things.
* **Machine translation has not been run against a paid key yet.** Every test
  goes through a stub; none opens a socket.
* **Project files store absolute paths** to the mod folders, so moving a project
  to another machine needs those paths set again.

## 🐞 Something broken?

Attach `pdx-translator.log` — it lives next to the executable and holds the
version, the environment and the traceback of whatever fell over.

---

Licence: [GNU GPL v3](https://github.com/Ajabald/pdx-translator/blob/main/LICENSE)
or later. Qt comes in through PySide6 under the LGPL —
[THIRD-PARTY.md](https://github.com/Ajabald/pdx-translator/blob/main/THIRD-PARTY.md).

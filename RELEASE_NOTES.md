An offline desktop workbench for translating the localisation of Paradox game
mods — a string table with statuses, translation memory, a term glossary,
mod-version diffing and configurable markup checks.

First public release.

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

* [**pdx-translator-setup-0.1.0.exe**](https://github.com/Ajabald/pdx-translator/releases/download/v0.1.0/pdx-translator-setup-0.1.0.exe) — installer *(recommended)*
* [**pdx-translator-v0.1.0.zip**](https://github.com/Ajabald/pdx-translator/releases/download/v0.1.0/pdx-translator-v0.1.0.zip) — portable, 50 MB

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

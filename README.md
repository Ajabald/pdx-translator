# PDX Translator

*[По-русски](README.ru.md)*

An offline desktop tool for translating the localisation of Paradox game mods —
a translator's workbench rather than a batch converter: a string table with
statuses, translation memory, a term glossary, mod-version diffing and
configurable markup checks.

Eight games of the series are supported, plus a custom one under any name. Pick
the game and the languages when creating a project.

> Version 0.1.0. The interface is available in English, Russian and Simplified
> Chinese — pick the language in «File → Preferences», it applies immediately.

## Features

- **A project is a single file** (`*.pdxproj`) holding strings, translations,
  memory and archive. Put it anywhere, copy it, hand it to someone else. On the
  «Projects» screen it can be shown in the file manager, dropped from the list
  (`Delete`) or deleted together with the file (`Shift+Delete`) — deletion goes
  to the recycle bin, so a misclick is recoverable.
- **Eight games of the series**: Crusader Kings III, Crusader Kings II, Europa
  Universalis IV, Europa Universalis V, Hearts of Iron IV, Stellaris,
  Victoria 3, Imperator: Rome — plus a custom game under any name if the format
  matches but the title is not on the list. Crusader Kings II uses the older CSV
  format; it is recognised by the data, not by the file name. Each game carries
  its own set of language folders, so you cannot pick a language that game does
  not have. Projects and memory databases live in per-game pens (`Projects\CK3`,
  `Bdd\CK3`): vanilla CK3 strings have no business being suggested to a
  Victoria 3 translator.
- **Mod updates**: after a rescan you see what the author changed — a summary
  split into meaningful and cosmetic edits, a «Δ» column in the table, changed
  words highlighted right in the source field, and the history of its revisions.
  Cosmetic edits (punctuation, case, whitespace) can be confirmed in bulk with a
  single action, and any operation can be undone (Ctrl+Z).
- **Translation memory** with attachable databases (`*.pdxtm`) in the `Bdd`
  folder: the game's vanilla localisation, the translation of a parent mod,
  exports of other projects. Matches are filled in automatically. Your own
  entries can be browsed, edited and deleted («Tools → Translation memory…», F9
  — the «Entries» tab).
- **Similar strings, not just exact matches.** The suggestion panel shows
  entries differing by a word or two, with a similarity score and the differences
  highlighted — when translating a submod on top of a mod there are almost no
  exact matches, but plenty of near ones. Plus the «How was this translated
  before…» search (Ctrl+Shift+F) over a selected fragment of the source: that is
  how you check how a name or a turn of phrase was handled already. The index
  lives inside the database; for databases built by earlier versions it is built
  by a button on the «Databases» tab of the memory window.
- **A glossary of terms, built by statistics and confirmed by you.** «Tools →
  Glossary…» (Shift+F9) counts word co-occurrence over the translation memory —
  the project's own plus every attached database — and offers pairs like
  `Maester → мейстер` with a confidence score and the number of pairs behind it.
  Russian word forms are grouped by stem, so `Таргариен` and `Таргариенов` add
  up instead of splitting the count; two-word terms are caught as well. Nothing
  reaches the translation on its own: you accept or reject each candidate, and a
  rejected one is not offered again. Accepted terms are highlighted in the
  original — hovering one shows its translation. See [The glossary](#the-glossary).
- **Machine translation** through six routes — DeepL, Claude, OpenAI, Google
  Cloud Translation, Yandex Translate, and manually through any web translator
  if you have no key. Markup is hidden from the service and put back afterwards,
  the result gets its own «Machine (unchecked)» status and always goes through
  the quality check. See [Machine translation](#machine-translation).
- **Editor**: edit in the cell or in the bottom panel, CK3 markup highlighting
  (`[GetTrait…]`, `$VAR$`, `#bold…#!`, `@gold!`), a file tree with progress,
  bulk operations, case-insensitive search.
- **A workbench**: a toolbar with the frequent actions, project languages and
  attached memory databases always visible in the header (databases are toggled
  from there in one click), light and dark themes switched on the fly. Every
  toolbar button has a menu item with the same shortcut, so everything is
  reachable both by mouse and from the keyboard; settings live in
  «File → Preferences…».
- **Column sorting**: click a header for ascending, again for descending, a
  third time to return to the original order (file and line number). Only one
  column is active at a time. On the «!» column the second click does not
  reverse the order but leaves only rows with issues — the same filter as the
  «with issues» checkbox and «Filters → Only with issues».
- **Quality checks you can tune**: issues show up in the «!» column next to the
  row — lost `$…$` variables and `@…!` icons, tags that diverged from the source,
  mismatched `\n` line breaks, double and edge spaces, a missing space before a
  substitution (`house[GetPlayer…]` renders as «houseStark» in game), a calque of
  the English copula (`tend to be [GetTrait…]` renders as «tend to be Loyalty»,
  because CK3 names traits with nouns), unbalanced quotes, one source with
  different translations. Any rule can be switched off, softened to a warning or
  granted leniencies; your own rules come in six kinds, and the whole set travels
  to another translator as a single file. See [Configuring the checks](#configuring-the-checks).
  A false positive is marked «not an error» and stops showing up; the full
  project report is F6.
- **Loading a translation from a mod** as a separate command («File → Load
  translation from mod…»): take someone else's translation of this mod, or your
  own edits made directly in the files. The rules (empty rows only or overwrite,
  whether to skip rows where the translation equals the source) are shown before
  writing, together with a preview, and the whole batch is undone with one Ctrl+Z.
- **Writing the translation to the mod** in the game's format: filenames and
  headers get the right language, UTF-8 with BOM, the source ordering and
  comments are preserved, unchanged files are not rewritten. The mod folder is
  remembered in the project separately from the folder the translation was
  imported from, and previous versions of overwritten files go to `backups` —
  outside the localisation tree, or the game would read the copies alongside the
  real files.

## Installing and running

Built version (Windows) — unpack the archive and run `pdx-translator.exe`.
No Python needed; the `Bdd` and `Projects` folders are created next to the
executable, so it can live on a flash drive.

From source (Python 3.11 or newer):

```
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pdxloc
```

Or double-click `run.bat`. Building the portable version:
`.venv\Scripts\pyinstaller.exe pdx-translator.spec` — the result is in `dist`.

## Quick start

1. **Create a project**: pick the game, the source folder (where `*_l_english.yml`
   files live), the translation folder and the languages.
2. **F5** — scan: the strings land in the table.
3. Translate: double-click the translation cell or edit in the bottom panel.
   `Ctrl+Enter` saves and moves to the next untranslated row.
4. **Ctrl+E** — write the translation to the mod: pick the mod folder. The choice
   is remembered in the project and offered next time.

## Translation memory databases

Mods copy hundreds of strings from the vanilla game and from the mods they build
on, so building the databases is the first thing worth doing:

- **vanilla**: «Translation memory → Build database», the folders
  `…\Crusader Kings III\game\localization\english` and
  `…\localization\<your language>`, type «Game database»;
- **the parent mod, if you translate a submod**: the mod's own localisation
  folder and the folder of its translation (usually a separate workshop mod,
  with files under `…\localization\<language>`), type «Someone else's translation».

Ready-made databases are **not shipped** with the application: that localisation
belongs to Paradox and to the authors of the translations. The tool builds them
from your copy of the game and your own subscriptions in seconds, and that is the
only lawful way to use them. Built databases are enabled on the «Databases» tab
of the same window, or straight from the window header.

## The glossary

A mod invents its own names, and the whole point of a glossary is that the same
name is translated the same way on page one and on page four hundred. Building
that list by hand is the boring half of the job, so «Tools → Glossary…»
(Shift+F9) proposes it from what you have already translated.

- **Candidates** are counted over the translation memory with the Dice
  coefficient of co-occurrence: a word of the original and a word of the
  translation that keep turning up in the same rows are likely each other's
  translation. Each candidate carries its confidence and the number of pairs it
  was seen in, so it is clear what the number rests on.
- **Statistics only suggests.** A candidate changes nothing anywhere until you
  accept it, and a rejected one is not offered again on the next run — your
  «no» is data too.
- **Accepted terms are highlighted** in the original field; hovering shows the
  accepted translation. The highlight coexists with the highlight of changes on
  an outdated row, and either can be switched off by its own checkbox.
- **Terms can be entered by hand** on the «Terms» tab — a term nobody proposed
  needs no confirming.
- **«Proper nouns only»** is on by default: only words written with a capital in
  the middle of a phrase are offered. That is what tells `Targaryen` apart from
  `Now` — both turn up capitalised, but only one of them does so mid-sentence.
  Switch it off and the list also fills with correct but useless pairs like
  «Now → теперь».

Three things the counting handles that a naive word count does not: Russian
word forms are grouped by stem (`Таргариен` / `Таргариенов` add up rather than
splitting the count), two-word translations are found (`Kingsguard` →
«Королевская гвардия»), and words that merely travel together are dropped — a
real term wins its translation by a margin, template noise does not.

## Machine translation

The service is chosen in «File → Preferences → Machine translation». Ctrl+M
translates a row, «Tools → Machine translation…» a batch of them.

| Route | Key required |
|---|---|
| DeepL | yes |
| Claude | yes |
| OpenAI | yes |
| Google Cloud Translation | yes |
| Yandex Translate | yes (plus a folder id) |
| Manually, through a web translator | no |
| Off | — |

The manual route is for those without a key: the application collects the rows
with numbered separators, you paste that text into any web translator and bring
the result back.

What matters here:

- **Markup is hidden from the service.** Every tag is replaced with a placeholder
  and restored after translation; lost placeholders end up in the report rather
  than in the mod files.
- **A batch is applied whole or not at all.** If the service's answer cannot be
  parsed, not a single row from that batch is written — a one-position shift
  would quietly ruin the entire block.
- **The result is marked «Machine (unchecked)».** Such a translation does not
  enter the translation memory, does not reach the mod without an explicit
  checkbox, always goes through the quality check, and stops being machine
  translation the moment a human touches the row.
- **The key is stored in the Windows settings, protected by DPAPI**
  (`CryptProtectData`). That keeps it away from prying eyes in the registry and
  makes copying the hive to another machine useless, but it does **not** protect
  against a program running under your own account. Paid services bill by
  characters — the batch size and the pause between requests are configured in
  the same place.

## Configuring the checks

«Checks → Configure checks…» (Shift+F6). What counts as an error depends on the
mod, the language and the stage of the work, so the rule set is not a constant:

- **17 built-in rules.** For each you can set whether it is on, its severity
  (error or warning) and its leniencies — for example, which inflection wrappers
  should not count as a bracket mismatch.
- **Your own rules** in six kinds: token multiset comparison, token count, a
  regular expression over the translation, one over the source–translation pair,
  character balance, and forbidden characters. A custom rule is configured
  entirely, message text and examples included.
- **Seven ready-made sets**: «Strict», «Breakage only», «Own», and one per game
  and language — «CK3 · Russian», «HOI4 · Russian», «CK2 · Russian»,
  «Stellaris · Russian». The difference is not cosmetic: on a live translation
  of 136 113 rows the strict set reports 41 713 issues, the built-in defaults
  37 040, «CK3 · Russian» 12 591 and «Breakage only» 11 404 (measured 2026-08-10).
- **Three layers**: built-in values, the global `qa_rules.json` next to the
  application, and the settings stored inside the project itself. Each layer
  keeps only the differences, so updating the application does not wipe your
  configuration.
- **Sharing a set** — the «Import…» and «Export…» buttons in the same window,
  a `.pdxqa` file. That is how a team agrees on what counts as an error. The file
  is self-contained: the chosen set, the differences from the built-in rules, and
  the custom rules in full.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| F5 / F6 / Ctrl+E | Scan / check the whole project / write translation to mod |
| Shift+F6 | Configure checks |
| Ctrl+Shift+F | How was this translated before (memory search) |
| F2, double click | Edit the translation in the cell |
| Ctrl+S | Save the translation (panel) |
| Ctrl+Enter | Save and go to the next untranslated row |
| Ctrl+D | Copy the source into the translation |
| F7 / F8 | Fill from memory / translation = source |
| Ctrl+M | Machine-translate the row |
| Ctrl+F6 | Apply to all rows with the same source |
| F10 / Shift+F10 | Validate / unvalidate |
| Ctrl+F10 / Ctrl+Shift+F10 | Custom status / ignore |
| F9 / Shift+F9 | Translation memory / glossary of terms |
| Ctrl+Z | Undo the last operation (a bulk edit) |
| Ctrl+F | Find |

## Row statuses

| Status | Colour | Meaning |
|---|---|---|
| Not translated | red | no translation |
| Machine (unchecked) | sand | translated by a service, unseen by a human |
| Auto (from memory) | yellow | filled from translation memory, needs review |
| Translated | green | the translation is saved |
| Reviewed | dark green | the translation is confirmed by hand |
| Stale | orange | the source changed after the translation (a diff is shown) |
| Ignored | grey-blue | nothing to translate (a row of bare tags, say) |
| Custom | purple | your own mark |

The percentage counts translated and reviewed rows against all rows except the
ignored ones. Translations of keys that vanished from the source are not lost —
they move to «Project → Archive of old translations…».

## How the files are laid out

```
pdx-translator/
├─ Projects/       projects (*.pdxproj) — one file per mod, one folder per game
│  └─ CK3/
├─ Bdd/            translation memory databases (*.pdxtm) — per game as well
│  └─ CK3/
├─ backups/        previous versions of files overwritten when writing to the mod
│                  (snapshots are named by time; anything else you put there
│                   is left alone)
├─ qa_rules.json   the global check configuration
├─ pdx-translator.log   the diagnostic log — attach it to a bug report
└─ run.bat
```

The project file is the source of truth, not the yml. Manual edits in yml files
are picked up on a rescan, but on a conflict the project wins (the scan report
names such cases).

## Command line

```
python -m pdxloc --project Projects\Mod.pdxproj --scan
python -m pdxloc --project Projects\New.pdxproj --create "Name" "path\english" "path\russian"
```

## Development

```
.venv\Scripts\python.exe -m pip install --group dev
.venv\Scripts\python.exe -m pytest -m "not realdata"
```

Tests marked `realdata` run against real localisation trees; the path comes from
the `PDXT_REALDATA` variable and they are excluded in CI. GUI tests run without a
screen — `QT_QPA_PLATFORM=offscreen`.

After editing interface strings, rebuild the translations:
`.venv\Scripts\python.exe tools\i18n.py all`.

Building the portable version: `pyinstaller pdx-translator.spec`.

## Licence

Copyright (C) 2026 Ajabald

This program is free software: you can redistribute it and/or modify it under
the terms of the [GNU General Public License](LICENSE) as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. It is distributed in the hope that it will be useful, but
**WITHOUT ANY WARRANTY** — without even the implied warranty of merchantability
or fitness for a particular purpose. See the GNU General Public License for more
details.

Forking and reworking is free; derivative works must stay under the same licence
with the source open.

Third-party components and their licences — [THIRD-PARTY.md](THIRD-PARTY.md).

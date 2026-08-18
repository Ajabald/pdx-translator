# Third-party components

PDX Translator itself is under the [GNU GPL v3 or later](LICENSE),
Copyright (C) 2026 Ajabald.

## PySide6 and Qt — GNU LGPL v3

The only runtime dependency is **PySide6**, the official Python binding for Qt.
Its wheel declares (checked on 6.11.1):

```
License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
```

That is a choice, and this project takes PySide6 and the Qt libraries it wraps
**under the GNU Lesser General Public License, version 3** — the option that
keeps Qt replaceable by the user, which is the point of the clause below.

- PySide6 — <https://doc.qt.io/qtforpython/licenses.html>
- Qt — <https://doc.qt.io/qt-6/licensing.html>
- LGPL v3 text — <https://www.gnu.org/licenses/lgpl-3.0.html>

GPL-3.0 and LGPL-3.0 are compatible, so the combined work is distributed under
the GPL; Qt itself remains under the LGPL.

### Why this matters for the portable build

Running from source pulls PySide6 from PyPI, and nothing is redistributed. The
**portable build is different**: PyInstaller puts Qt inside the archive — about
93 MB of the 120 — so whoever hands out that archive is redistributing Qt and
owes its recipients the LGPL notice.

Two things keep that obligation met:

1. **This file and the «About» window** name Qt and its licence.
2. **The build is `onedir`, not `onefile`.** Qt ships as separate DLLs next to
   the executable, so anyone may replace them with their own build of the same
   version — which is exactly what LGPL §4 asks for. A single-file build would
   have made that hard, and it was rejected for other reasons anyway (slow start
   and antivirus false positives — see `pdx-translator.spec`).

**The LGPL text has to be added by hand.** Checked on PySide6 6.11.1: the wheels
ship exactly one licence file, `LicenseRef-Qt-Commercial.txt`, in
`.venv\Lib\site-packages\pyside6*-*.dist-info\licenses\` — the LGPL text is not
in there at all. So packaging a release means downloading
<https://www.gnu.org/licenses/lgpl-3.0.txt> and putting it next to the
executable as `LICENSE.LGPL-3.0.txt`, together with a copy of this file.

This is a step in the build checklist of [ACCEPTANCE.md](ACCEPTANCE.md), not an
automatic part of `pdx-translator.spec`: forgetting it breaks an obligation, and
an obligation is worth a line a human reads rather than a line a script hides.

## Development-only tools

Not redistributed — they never reach the user, and are listed for completeness:

| Tool | Licence |
|---|---|
| pytest, pytest-qt | MIT |
| PyInstaller | GPL v2 or later, with an exception permitting proprietary output |
| ruff | MIT |

## What is *not* shipped

**Translation memory databases are never included in a release.** The
localisation inside them belongs to Paradox Interactive and to the authors of
the community translations. The tool builds such a database from the user's own
copy of the game in seconds — see «Translation memory databases» in the
[README](README.md).

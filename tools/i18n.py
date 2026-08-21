"""Building the interface translations: the sources -> .ts -> .qm.

    .venv\\Scripts\\python.exe tools\\i18n.py update    # refresh the .ts from the code
    .venv\\Scripts\\python.exe tools\\i18n.py release   # build the .qm out of the .ts
    .venv\\Scripts\\python.exe tools\\i18n.py all

`pyside6-lupdate` and `pyside6-lrelease` lie in the venv — no new dependencies
are needed. `.py` is not in the default list of lupdate extensions (it is meant
for C++), so `-extensions py` is always passed.

There is no English file on purpose: the strings in the code are English as it
is, and an empty `pdxloc_en.qm` would only confuse — `gui/language.py` counts a
language as available by the presence of a file.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "pdxloc"
TS_DIR = SRC / "gui" / "translations"
SCRIPTS = ROOT / ".venv" / "Scripts"

# English is the language of the original, it has no file (see gui/language.SOURCE)
TARGETS = ("ru", "zh_CN")


def _tool(name: str) -> str:
    exe = SCRIPTS / f"pyside6-{name}.exe"
    return str(exe) if exe.exists() else f"pyside6-{name}"


def _sources() -> list[str]:
    return [str(p) for p in sorted(SRC.rglob("*.py"))]


def update() -> None:
    """Pull the strings out of the code into .ts, keeping the translations already made."""
    TS_DIR.mkdir(parents=True, exist_ok=True)
    for code in TARGETS:
        ts = TS_DIR / f"pdxloc_{code}.ts"
        cmd = [
            _tool("lupdate"),
            "-extensions", "py",
            # relative paths to the sources: otherwise a path with the user name
            # travels into the .ts, and the file cannot be shown to a translator
            "-locations", "relative",
            # We do not keep obsolete records. The pairs «original → translation»
            # live in tools/*_translations.py, and the .ts is for us a derivative
            # of the code; leave lupdate to mark the thrown-out strings
            # `vanished`, and they will demand a pair in both languages forever.
            # Reworded a string — the old one goes, and its pair has to go too,
            # which is what the tests will say.
            "-no-obsolete",
            *_sources(),
            "-ts", str(ts),
        ]
        print(f"-> {ts.name}")
        subprocess.run(cmd, check=True, cwd=ROOT)


def release() -> None:
    """Compile the .ts into .qm — those are what the application reads."""
    for ts in sorted(TS_DIR.glob("pdxloc_*.ts")):
        qm = ts.with_suffix(".qm")
        print(f"-> {qm.name}")
        subprocess.run([_tool("lrelease"), str(ts), "-qm", str(qm)],
                       check=True, cwd=ROOT)


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    if command in ("update", "all"):
        update()
    if command in ("release", "all"):
        release()
    if command not in ("update", "release", "all"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

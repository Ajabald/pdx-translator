"""Сборка переводов интерфейса: исходники -> .ts -> .qm.

    .venv\\Scripts\\python.exe tools\\i18n.py update    # обновить .ts из кода
    .venv\\Scripts\\python.exe tools\\i18n.py release   # собрать .qm из .ts
    .venv\\Scripts\\python.exe tools\\i18n.py all

`pyside6-lupdate` и `pyside6-lrelease` лежат в venv — новых зависимостей не
нужно. `.py` не входит в список расширений lupdate по умолчанию (он рассчитан
на C++), поэтому `-extensions py` передаётся всегда.

Английского файла нет намеренно: строки в коде и так английские, и пустой
`pdxloc_en.qm` только сбивал бы с толку — `gui/language.py` считает язык
доступным по наличию файла.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "pdxloc"
TS_DIR = SRC / "gui" / "translations"
SCRIPTS = ROOT / ".venv" / "Scripts"

# Английский — язык оригинала, его файла нет (см. gui/language.SOURCE)
TARGETS = ("ru", "zh_CN")


def _tool(name: str) -> str:
    exe = SCRIPTS / f"pyside6-{name}.exe"
    return str(exe) if exe.exists() else f"pyside6-{name}"


def _sources() -> list[str]:
    return [str(p) for p in sorted(SRC.rglob("*.py"))]


def update() -> None:
    """Вытащить строки из кода в .ts, сохранив уже сделанные переводы."""
    TS_DIR.mkdir(parents=True, exist_ok=True)
    for code in TARGETS:
        ts = TS_DIR / f"pdxloc_{code}.ts"
        cmd = [
            _tool("lupdate"),
            "-extensions", "py",
            # относительные пути к исходникам: иначе в .ts уезжает путь с
            # именем пользователя, и файл нельзя показать переводчику
            "-locations", "relative",
            # Устаревшие записи не храним. Пары «оригинал → перевод» живут в
            # tools/*_translations.py, и .ts для нас — производная от кода;
            # оставь lupdate помечать выброшенные строки `vanished`, и они
            # навсегда потребуют пары в обоих языках. Переформулировал строку —
            # старая уходит, и её пару надо убрать, о чём и скажут тесты.
            "-no-obsolete",
            *_sources(),
            "-ts", str(ts),
        ]
        print(f"-> {ts.name}")
        subprocess.run(cmd, check=True, cwd=ROOT)


def release() -> None:
    """Скомпилировать .ts в .qm — их и читает приложение."""
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

"""Общие фикстуры: генератор синтетических деревьев локализации и in-memory БД."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Приёмочные тесты идут по настоящим деревьям локализации. Путь задаётся
# переменной CK3T_REALDATA; по умолчанию — папка над репозиторием, где эти
# деревья и лежат у автора. Прописывать сюда конкретный диск нельзя: файл
# уезжает в публичный репозиторий.
REALDATA_ROOT = Path(os.environ.get("CK3T_REALDATA") or Path(__file__).parents[2])
REALDATA_EN = REALDATA_ROOT / "localization en" / "replace" / "english"
REALDATA_RU = REALDATA_ROOT / "localization ru" / "replace" / "russian"


def realdata_available() -> bool:
    return REALDATA_EN.is_dir() and REALDATA_RU.is_dir()


requires_realdata = pytest.mark.realdata


@pytest.fixture
def make_tree(tmp_path):
    """Создать дерево файлов локализации с BOM.

    spec: dict относительный_путь -> текст файла (без BOM, он добавится).
    Возвращает корень дерева.
    """
    def _make(spec: dict[str, str], subdir: str = "tree") -> Path:
        root = tmp_path / subdir
        for rel, text in spec.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8-sig", newline="\n") as f:
                f.write(text)
        root.mkdir(parents=True, exist_ok=True)
        return root

    return _make


@pytest.fixture(autouse=True)
def isolated_backups(tmp_path, monkeypatch):
    """Бэкапы записи перевода — во временную папку.

    Иначе любой тест, экспортирующий поверх существующих файлов, оставляет
    снимки в рабочей папке backups приложения.
    """
    from ck3loc import settings

    monkeypatch.setattr(settings, "backups_dir", lambda: tmp_path / "backups")


@pytest.fixture
def db():
    from ck3loc.db import init_schema, register_functions

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    register_functions(conn)
    init_schema(conn)
    yield conn
    conn.close()

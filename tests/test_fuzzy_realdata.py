"""The speed of the search for similar rows on a real database.

Synthetics say nothing about the time: the bottleneck is a full-text query over
hundreds of thousands of records. We take the vanilla CK3 database out of the Bdd
folder, copy it into a temporary folder (the user's file we do not touch) and
measure on it.
"""
from __future__ import annotations

import shutil
import time

import pytest

from pdxloc import project
from pdxloc.core import fuzzy, tm_import

pytestmark = pytest.mark.realdata

# The query goes at every move to a row, so the budget is that of a redraw.
# Measured on the vanilla database (244 thousand records): ~16 ms, threefold room.
BUDGET_MS = 50


def _biggest_base():
    # the databases lie in the pens of their games, and the old ones in the root of Bdd
    bases = project.all_tm_databases()
    if not bases:
        return None
    return max(bases, key=lambda item: int(item[1].get("entries", 0) or 0))


@pytest.fixture(scope="module")
def indexed_base(tmp_path_factory):
    found = _biggest_base()
    if found is None:
        pytest.skip("в папке Bdd нет баз памяти переводов")
    path, meta = found
    if int(meta.get("entries", 0) or 0) < 10_000:
        pytest.skip("базы слишком малы, замер бессмысленен")
    copy = tmp_path_factory.mktemp("bdd") / path.name
    shutil.copy2(path, copy)
    tm_import.build_fts_index(copy)
    return copy, int(meta["entries"])


def test_similar_lookup_is_fast(indexed_base, tmp_path):
    path, entries = indexed_base
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root="e", tgt_root="r")
    try:
        project.attach_tm_sources(conn, [path])
        queries = [
            "The Bridge Must Be Paid",
            "Send down a dozen more spears to quiet the crowd.",
            "You are a member of the Kingsguard",
            "Grant the land to your loyal vassal",
        ]
        for q in queries:                       # warming the page cache
            fuzzy.lookup_similar(conn, q)

        started = time.perf_counter()
        for q in queries:
            fuzzy.lookup_similar(conn, q)
        per_query_ms = (time.perf_counter() - started) / len(queries) * 1000
    finally:
        conn.close()

    print(f"\nбаза {entries} записей · {per_query_ms:.1f} мс на запрос")
    assert per_query_ms < BUDGET_MS

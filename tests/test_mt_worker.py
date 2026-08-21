"""The machine translation thread: its own connection, its own contract of signals.

The module had not been covered at all until now, and it is more dangerous than
its neighbours: the rule of threads in this application is **one connection per
thread**, and `MtWorker` opens its own, writes into the project database with it
and is obliged to close it. There is nowhere but here to check that.

The network is not opened here even once: the provider is substituted by a stub of
the same shape as in `test_mt_dialog.py`.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project as project_mod  # noqa: E402
from pdxloc.core import mt, mt_run  # noqa: E402
from pdxloc.core.mt_providers import ProviderConfig  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.gui import mt_worker  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'


class Shouty:
    """A stub of a provider — the shape is the same as the real ones have."""

    name = "shouty"
    label = "Shouty"
    char_limit = 1000

    def __init__(self, config=None, fail: bool = False):
        self.config = config
        self.fail = fail

    def supports(self, src_locale, tgt_locale) -> bool:
        return True

    def translate_batch(self, texts, src_locale, tgt_locale):
        if self.fail:
            raise RuntimeError("сервис отказал")
        return [t.upper() for t in texts]


@pytest.fixture
def live(tmp_path, make_tree):
    """A real project file: the worker opens it itself, by the path."""
    from pdxloc.core.scanner import scan_project

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project_mod.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    rows = [mt_run.MtRow(unit_id=r["id"], key=r["key"], text=r["en_text"])
            for r in conn.execute(
                "SELECT id, key, en_text FROM units WHERE en_text IS NOT NULL "
                "ORDER BY id")]
    assert rows, "проект без строк — проверять нечего"
    yield conn, path, rows
    conn.close()


@pytest.fixture
def worker_of(live, monkeypatch, qtbot):
    """Assemble a worker with a substituted provider and drive it to the end."""
    _conn, path, rows = live

    def run(*, fail: bool = False):
        monkeypatch.setattr(mt, "get_provider",
                            lambda name, config: Shouty(config, fail=fail))
        worker = mt_worker.MtWorker(
            path, rows, "shouty", ProviderConfig(), "en", "ru", "batch-1",
            throttle_ms=0, retries=1)
        thread = mt_worker.start(worker, None)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        # We wait for exactly `finished`, even when the provider refuses: a refusal
        # of a batch is not fatal to the run, `mt_run` writes it into the report
        # and goes on. `failed` is left for what flew out of the run whole — for
        # example, the project file did not open.
        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            thread.start()
        qtbot.waitUntil(lambda: thread.isFinished(), timeout=5000)
        return blocker.args[0]

    return run


# --- the contract of signals -----------------------------------------------


def test_cancellation_is_a_field_of_the_report_not_a_signal() -> None:
    """This worker has no `cancelled` — and that is a decision, not forgetfulness.

    For its neighbours (`ScanWorker`, `_BuildWorker`) a cancellation is terminal
    and comes instead of `finished`. Here the rows that managed to get translated
    are already in the database, and a human is obliged to see the summary over
    them — so a cancellation is not a state of the run but a property of the
    result.
    """
    assert not hasattr(mt_worker.MtWorker, "cancelled")
    assert "cancelled" in mt_run.MtReport.__dataclass_fields__


def test_neighbours_do_have_the_terminal_signal() -> None:
    """A watchman of the other side: where a cancellation is terminal, the signal stays.

    Otherwise «we removed what was superfluous» will one day be read as «the signal
    is not needed here at all» and taken off the scanner, where it is the only way
    to learn about a cancellation.
    """
    from pdxloc.gui.scan_dialog import ScanWorker
    from pdxloc.gui.tm_build_tab import _BuildWorker

    assert hasattr(ScanWorker, "cancelled")
    assert hasattr(_BuildWorker, "cancelled")


def test_the_summary_says_a_run_was_interrupted() -> None:
    """Since there is no signal, the fact of a cancellation is obliged to show in the summary."""
    report = mt_run.MtReport(rows_sent=5, rows_translated=2, cancelled=True)
    assert "Ctrl+Z" in report.summary()


# --- the work in a thread --------------------------------------------------


def test_the_worker_writes_with_its_own_connection(live, worker_of) -> None:
    conn, _path, rows = live
    report = worker_of()

    assert report.rows_translated == len(rows)
    assert not report.cancelled

    # the connection of the fixture took no part in the writing — we reread with it
    written = conn.execute(
        "SELECT ru_text, status FROM units WHERE ru_text IS NOT NULL").fetchall()
    assert len(written) == len(rows)
    assert all(r["ru_text"].isupper() for r in written)
    assert {r["status"] for r in written} == {Status.MACHINE.value}


def test_a_failing_service_lands_in_the_report_not_in_a_crash(live, worker_of) -> None:
    """A refusal of the service is a line of the report, not a crash of the thread.

    The run goes in batches, and a fallen batch is no reason to abandon the rest:
    what did not get translated is listed in `failures`, and a human sees that in
    the summary.
    """
    conn, _path, rows = live
    report = worker_of(fail=True)

    assert report.rows_failed == len(rows)
    assert report.rows_translated == 0
    assert report.failures, "провал обязан быть назван поимённо"
    assert "Rows not translated" in report.summary()

    # and nothing went into the database at that
    left = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    assert left == 0


def test_the_project_file_is_released(live, worker_of) -> None:
    """The connection of the worker is obliged to close — otherwise the project file is not let go.

    On Windows that is no abstraction: an unclosed handle will let one neither
    delete the project nor rename it.
    """
    conn, path, _rows = live
    worker_of()

    conn.close()
    moved = path.with_suffix(".moved")
    path.replace(moved)             # would have fallen over on a live handle
    assert moved.is_file()

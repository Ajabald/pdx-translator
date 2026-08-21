"""The machine translation run: the batches, the refusals, the cancellation, the rollback.

Not one test here opens a socket or really sleeps: the providers are stubs, and
`time.sleep` is substituted. The suite is driven thousands of times, and a minute
of waiting in the backoff would turn it into something people stop running.

The main thing watched over: **a batch that could not be parsed is not applied by
a single row**. A translation landed on a foreign key looks like work done and
gets found weeks later.
"""
from __future__ import annotations

import pytest

from pdxloc.core import mt_run, unit_ops
from pdxloc.core.mt_errors import MtAuthError, MtQuotaError
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_run import MtRow
from pdxloc.core.statuses import Status

from test_scanner import get_unit, make_project


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """The backoff we check by logic, not by waiting."""
    monkeypatch.setattr(mt_run.time, "sleep", lambda *_: None)


class Upper:
    """A stub of a provider: returns the text in upper case."""

    name = "upper"
    label = "Upper"
    char_limit = 1000

    def __init__(self, config: ProviderConfig | None = None):
        self.calls: list[list[str]] = []

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return True

    def translate_batch(self, texts, src_locale, tgt_locale):
        self.calls.append(list(texts))
        return [t.upper() for t in texts]


class Failing(Upper):
    """Refuses a set number of times, then works."""

    def __init__(self, error, times=1):
        super().__init__()
        self._error = error
        self._left = times

    def translate_batch(self, texts, src_locale, tgt_locale):
        if self._left > 0:
            self._left -= 1
            raise self._error
        return super().translate_batch(texts, src_locale, tgt_locale)


def rows(*texts: str) -> list[MtRow]:
    return [MtRow(unit_id=i + 1, key=f"k{i}", text=t) for i, t in enumerate(texts)]


def collect():
    """A receiver of the write: (row, translation)."""
    written: list[tuple[int, str]] = []
    return written, lambda row, text: written.append((row.unit_id, text))


# --- laying out into batches ---

def test_batches_respect_the_character_budget() -> None:
    batches, oversized = mt_run.plan_batches(["a" * 30] * 5, budget=70)
    assert [len(b) for b in batches] == [2, 2, 1]
    assert oversized == []


def test_batches_respect_the_row_limit() -> None:
    batches, _ = mt_run.plan_batches(["x"] * 120, budget=1_000_000)
    assert all(len(b) <= mt_run.MAX_ROWS_PER_BATCH for b in batches)
    assert sum(len(b) for b in batches) == 120


def test_indexes_are_returned_in_order() -> None:
    """The matching goes by position: identical originals would get mixed up otherwise."""
    batches, _ = mt_run.plan_batches(["Gold", "Gold", "Gold"], budget=8)
    assert [i for batch in batches for i in batch] == [0, 1, 2]


def test_a_single_row_over_budget_gets_its_own_batch() -> None:
    batches, oversized = mt_run.plan_batches(["a" * 100, "b"], budget=50)
    assert oversized == []
    assert batches == [[0], [1]]


def test_a_row_over_the_hard_limit_is_never_cut() -> None:
    """A trim would look like a success while losing half the meaning."""
    batches, oversized = mt_run.plan_batches(
        ["a" * 500, "ok"], budget=1000, hard_limit=100)
    assert oversized == [0]
    assert batches == [[1]]


# --- a successful run ---

def test_run_translates_and_writes_every_row() -> None:
    written, write = collect()
    report = mt_run.run(Upper(), rows("one", "two"), "en", "ru",
                        write=write, throttle_ms=0)
    assert written == [(1, "ONE"), (2, "TWO")]
    assert (report.rows_translated, report.rows_failed) == (2, 0)
    assert report.characters == 6
    assert report.requests == 1


def test_markup_survives_the_round_trip() -> None:
    """The provider sees a placeholder and not markup, and returns it untouched."""
    provider = Upper()
    written, write = collect()
    mt_run.run(provider, rows("Gain [GetName] and @gold!"), "en", "ru",
               write=write, throttle_ms=0)
    sent = provider.calls[0][0]
    assert "[GetName]" not in sent and "@gold!" not in sent
    assert written[0][1] == "GAIN [GetName] AND @gold!"


def test_lost_placeholder_is_reported_but_the_row_is_still_written() -> None:
    """A human has to see the broken row — so it has to exist."""
    class Dropper(Upper):
        def translate_batch(self, texts, src_locale, tgt_locale):
            return ["перевод без меток" for _ in texts]

    written, write = collect()
    report = mt_run.run(Dropper(), rows("Gain [GetName]"), "en", "ru",
                        write=write, throttle_ms=0)
    assert written == [(1, "перевод без меток")]
    assert report.rows_translated == 1
    assert len(report.placeholders_lost) == 1
    assert report.placeholders_lost[0][:2] == (1, "k0")


# --- the refusals ---

def test_a_batch_that_failed_is_not_applied_at_all() -> None:
    """Not a single row: there is nothing to parse the correspondence by, and guessing will not do."""
    written, write = collect()
    report = mt_run.run(Failing(MtAuthError("ключ не принят"), times=99),
                        rows("one", "two", "three"), "en", "ru",
                        write=write, throttle_ms=0)
    assert written == []
    assert report.rows_failed == 3
    assert report.rows_translated == 0
    assert all("ключ не принят" in message for _, _, message in report.failures)


def test_quota_error_is_retried_and_then_succeeds() -> None:
    provider = Failing(MtQuotaError("лимит", retry_after=1.0), times=2)
    written, write = collect()
    report = mt_run.run(provider, rows("one"), "en", "ru",
                        write=write, throttle_ms=0, retries=3)
    assert written == [(1, "ONE")]
    assert report.rows_failed == 0


def test_quota_error_gives_up_after_the_last_retry() -> None:
    provider = Failing(MtQuotaError("лимит"), times=99)
    written, write = collect()
    report = mt_run.run(provider, rows("one"), "en", "ru",
                        write=write, throttle_ms=0, retries=2)
    assert written == []
    assert report.rows_failed == 1


def test_wrong_key_is_not_retried() -> None:
    """A retry will not mend it, but will spend the time."""
    provider = Failing(MtAuthError("ключ"), times=99)
    mt_run.run(provider, rows("one"), "en", "ru",
               write=lambda *_: None, throttle_ms=0, retries=5)
    assert provider._left == 98      # exactly one attempt


def test_a_failing_batch_does_not_stop_the_rest() -> None:
    class EverySecond(Upper):
        def __init__(self):
            super().__init__()
            self.n = 0

        def translate_batch(self, texts, src_locale, tgt_locale):
            self.n += 1
            if self.n == 1:
                raise MtAuthError("сбой")
            return super().translate_batch(texts, src_locale, tgt_locale)

    written, write = collect()
    report = mt_run.run(EverySecond(), rows("aaa", "bbb"), "en", "ru",
                        write=write, budget=3, throttle_ms=0)
    assert report.rows_failed == 1 and report.rows_translated == 1
    assert written == [(2, "BBB")]


# --- the cancellation ---

def test_cancel_keeps_what_was_already_written() -> None:
    state = {"stop": False}

    class StopsAfterFirst(Upper):
        def translate_batch(self, texts, src_locale, tgt_locale):
            result = super().translate_batch(texts, src_locale, tgt_locale)
            state["stop"] = True
            return result

    written, write = collect()
    report = mt_run.run(StopsAfterFirst(), rows("aaa", "bbb"), "en", "ru",
                        write=write, budget=3, throttle_ms=0,
                        should_cancel=lambda: state["stop"])
    assert report.cancelled
    assert written == [(1, "AAA")]
    assert "Ctrl+Z" in report.summary()


# --- the write into the database and the rollback ---

def test_machine_rows_land_in_one_undoable_batch(db, make_tree) -> None:
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n b:0 "World"\n'},
                   "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    from pdxloc.core.scanner import scan_project
    scan_project(db, pid)

    batch = unit_ops.new_batch_id()
    units = {r["key"]: r["id"] for r in db.execute("SELECT key, id FROM units")}
    payload = [MtRow(unit_id=units["a"], key="a", text="Hello"),
               MtRow(unit_id=units["b"], key="b", text="World")]

    mt_run.run(Upper(), payload, "en", "ru", throttle_ms=0,
               write=lambda row, text: unit_ops.save_machine_text(
                   db, row.unit_id, text, batch_id=batch))

    assert get_unit(db, "a")["status"] == Status.MACHINE.value
    assert get_unit(db, "a")["ru_text"] == "HELLO"
    assert unit_ops.last_batch(db) == (batch, "machine", 2)

    assert unit_ops.undo_batch(db, batch) == 2
    assert get_unit(db, "a")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "a")["ru_text"] is None


def test_machine_text_never_reaches_the_memory(db, make_tree) -> None:
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    from pdxloc.core.scanner import scan_project
    scan_project(db, pid)

    unit_id = get_unit(db, "a")["id"]
    unit_ops.save_machine_text(db, unit_id, "Привет",
                               batch_id=unit_ops.new_batch_id())
    assert db.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0] == 0


def test_empty_machine_text_is_not_written(db, make_tree) -> None:
    """A «Machine» status without text would mean the row is filled."""
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    from pdxloc.core.scanner import scan_project
    scan_project(db, pid)

    unit_id = get_unit(db, "a")["id"]
    assert not unit_ops.save_machine_text(db, unit_id, "   ",
                                          batch_id=unit_ops.new_batch_id())
    assert get_unit(db, "a")["status"] == Status.UNTRANSLATED.value
    assert unit_ops.last_batch(db) is None


def test_report_summary_mentions_the_broken_rows() -> None:
    report = mt_run.MtReport(rows_translated=3, rows_failed=1)
    report.placeholders_lost.append((1, "k", ["⟦0⟧"]))
    text = report.summary()
    assert "3" in text and "1" in text

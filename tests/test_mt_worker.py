"""Поток машинного перевода: своё соединение, свой контракт сигналов.

Модуль до сих пор не был покрыт вовсе, а он опаснее соседей: правило потоков в
этом приложении — **одно соединение на поток**, и `MtWorker` открывает своё,
пишет им в базу проекта и обязан его закрыть. Проверить это, кроме как здесь,
негде.

Сеть тут не открывается ни разу: провайдер подменяется заглушкой той же формы,
что в `test_mt_dialog.py`.
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
    """Заглушка провайдера — форма та же, что у настоящих."""

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
    """Настоящий файл проекта: воркер открывает его сам, по пути."""
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
    """Собрать воркера с подменённым провайдером и прогнать до конца."""
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
        # Ждём именно `finished`, даже когда провайдер отказывает: отказ пачки
        # для прогона не фатален, `mt_run` записывает его в отчёт и идёт
        # дальше. `failed` остаётся для того, что вылетело из прогона целиком —
        # например, не открылся файл проекта.
        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            thread.start()
        qtbot.waitUntil(lambda: thread.isFinished(), timeout=5000)
        return blocker.args[0]

    return run


# --- контракт сигналов -----------------------------------------------------


def test_cancellation_is_a_field_of_the_report_not_a_signal() -> None:
    """У этого воркера `cancelled` нет — и это решение, а не забывчивость.

    У соседей (`ScanWorker`, `_BuildWorker`) отмена терминальна и приходит
    вместо `finished`. Здесь строки, успевшие перевестись, уже в базе, и сводку
    по ним человек обязан увидеть — значит отмена не состояние прогона, а
    свойство результата.
    """
    assert not hasattr(mt_worker.MtWorker, "cancelled")
    assert "cancelled" in mt_run.MtReport.__dataclass_fields__


def test_neighbours_do_have_the_terminal_signal() -> None:
    """Сторож обратной стороны: у кого отмена терминальна, сигнал остаётся.

    Иначе «убрали лишнее» однажды прочитают как «сигнал тут не нужен вообще» и
    снимут его у сканера, где он единственный способ узнать об отмене.
    """
    from pdxloc.gui.scan_dialog import ScanWorker
    from pdxloc.gui.tm_build_tab import _BuildWorker

    assert hasattr(ScanWorker, "cancelled")
    assert hasattr(_BuildWorker, "cancelled")


def test_the_summary_says_a_run_was_interrupted() -> None:
    """Раз сигнала нет, факт отмены обязан быть виден в сводке."""
    report = mt_run.MtReport(rows_sent=5, rows_translated=2, cancelled=True)
    assert "Ctrl+Z" in report.summary()


# --- работа в потоке -------------------------------------------------------


def test_the_worker_writes_with_its_own_connection(live, worker_of) -> None:
    conn, _path, rows = live
    report = worker_of()

    assert report.rows_translated == len(rows)
    assert not report.cancelled

    # соединение фикстуры в записи не участвовало — перечитываем им
    written = conn.execute(
        "SELECT ru_text, status FROM units WHERE ru_text IS NOT NULL").fetchall()
    assert len(written) == len(rows)
    assert all(r["ru_text"].isupper() for r in written)
    assert {r["status"] for r in written} == {Status.MACHINE.value}


def test_a_failing_service_lands_in_the_report_not_in_a_crash(live, worker_of) -> None:
    """Отказ сервиса — строка отчёта, а не падение потока.

    Прогон идёт пачками, и упавшая пачка не повод бросать остальные: то, что не
    перевелось, перечислено в `failures`, а человек видит это в сводке.
    """
    conn, _path, rows = live
    report = worker_of(fail=True)

    assert report.rows_failed == len(rows)
    assert report.rows_translated == 0
    assert report.failures, "провал обязан быть назван поимённо"
    assert "Rows not translated" in report.summary()

    # в базу при этом не ушло ничего
    left = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    assert left == 0


def test_the_project_file_is_released(live, worker_of) -> None:
    """Соединение воркера обязано закрыться — иначе файл проекта не отпустить.

    На Windows это не абстракция: незакрытый дескриптор не даст ни удалить
    проект, ни переименовать его.
    """
    conn, path, _rows = live
    worker_of()

    conn.close()
    moved = path.with_suffix(".moved")
    path.replace(moved)             # упало бы на живом дескрипторе
    assert moved.is_file()

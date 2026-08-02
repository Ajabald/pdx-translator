"""Фоновые операции не должны вешать окно.

Две разные причины зависания, обе уже случались:

* обработчик завершения вызывал thread.wait() из основного потока, а сигнал
  «готово» приходит раньше, чем run() отдаёт управление — quit() не успевал
  подействовать и ожидание становилось вечным;
* сигнал был подключён к лямбде. Лямбда — не QObject, и PySide вызывает её
  напрямую в потоке отправителя, поэтому обработчик трогал виджеты из рабочего
  потока: окно вставало намертво на 99%, оба окна получали «Не отвечает».
"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'


@pytest.fixture
def loc_tree(tmp_path):
    loc = tmp_path / "game" / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"m_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    return loc


def test_tm_build_dialog_finishes_without_hanging(loc_tree, tmp_path, qtbot, monkeypatch):
    from ck3loc import settings
    from ck3loc.gui.tm_import_dialog import TmImportDialog

    bdd = tmp_path / "Bdd"
    bdd.mkdir()
    monkeypatch.setattr(settings, "bdd_dir", lambda: bdd)

    class Watched(TmImportDialog):
        """Запоминает, в каком потоке отработал обработчик завершения."""

        done_tid = None

        def _on_done(self, report):
            self.done_tid = threading.get_ident()
            super()._on_done(report)

    dlg = Watched()
    qtbot.addWidget(dlg)
    dlg.name_edit.setText("Тест")
    dlg.src_edit.setText(str(loc_tree / "english"))
    dlg.tgt_edit.setText(str(loc_tree / "russian"))

    dlg._run()
    qtbot.waitUntil(lambda: dlg.report_box.isVisibleTo(dlg), timeout=15000)

    # обработчик завершения обязан выполняться в потоке GUI, иначе окно виснет
    assert dlg.done_tid == threading.get_ident()
    assert "Пар переводов: 2" in dlg.report_box.toPlainText()
    # поток должен остановиться сам, без ожидания из основного
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)
    assert (bdd / "Тест_english-russian.ck3tm").is_file()


def test_scan_dialog_finishes_without_hanging(tmp_path, make_tree, qtbot):
    from ck3loc import project
    from ck3loc.gui.scan_dialog import ScanProgressDialog

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.close()

    dlg = ScanProgressDialog(path, [])
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg.stats is not None or dlg.error is not None, timeout=15000)
    assert dlg.error is None
    assert dlg.stats.new == 2
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)


def test_scan_can_be_cancelled(tmp_path, make_tree, qtbot):
    from ck3loc import project
    from ck3loc.gui.scan_dialog import ScanProgressDialog

    en = make_tree({f"f{i}_l_english.yml": EN for i in range(40)}, "en")
    ru = make_tree({}, "ru")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.close()

    dlg = ScanProgressDialog(path, [])
    qtbot.addWidget(dlg)
    dlg._on_cancel()
    qtbot.waitUntil(lambda: dlg.was_cancelled or dlg.stats is not None, timeout=15000)
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)


def test_no_worker_signal_is_connected_to_a_lambda():
    """Сигналы фонового объекта — только на связанные методы окна.

    PySide вызывает лямбду напрямую в потоке отправителя, поэтому такая связка
    незаметно уводит работу с виджетами в рабочий поток.
    """
    import re
    from pathlib import Path

    gui = Path(__file__).resolve().parents[1] / "src" / "ck3loc" / "gui"
    bad = []
    for path in sorted(gui.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "moveToThread" not in text:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r"_worker\.\w+\.connect\(\s*lambda", line):
                bad.append(f"{path.name}:{n}: {line.strip()}")
    assert not bad, "сигнал рабочего потока подключён к лямбде:\n" + "\n".join(bad)


def test_standard_buttons_are_russian(qtbot):
    """Кнопки Qt («Close», «Yes», «No») должны быть на русском."""
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from ck3loc.app import _install_qt_translations

    _install_qt_translations(QApplication.instance())
    box = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Ok)
    qtbot.addWidget(box)
    close_text = box.button(QDialogButtonBox.Close).text().replace("&", "")
    assert close_text == "Закрыть", f"кнопка осталась английской: {close_text}"

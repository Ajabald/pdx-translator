"""Background operations must not hang the window.

Two different causes of a hang, both of which have already happened:

* the completion handler called thread.wait() from the main thread, while the
  «ready» signal arrives before run() gives control back — quit() had no time to
  take effect and the wait became eternal;
* the signal was connected to a lambda. A lambda is no QObject, and PySide calls
  it directly in the thread of the sender, so the handler touched widgets from the
  worker thread: the window stood dead at 99%, and both windows got «Not
  responding».
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
    from pdxloc import settings
    from pdxloc.gui.tm_build_tab import TmBuildTab

    bdd = tmp_path / "Bdd"
    bdd.mkdir()
    monkeypatch.setattr(settings, "bdd_dir", lambda: bdd)

    class Watched(TmBuildTab):
        """Remembers which thread the completion handler ran in."""

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

    # the completion handler is obliged to run in the GUI thread, otherwise the window hangs
    assert dlg.done_tid == threading.get_ident()
    assert "Translation pairs: 2" in dlg.report_box.toPlainText()
    # the thread has to stop by itself, without a wait from the main one
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)
    # the database lands in the pen of its game (see core/games.py)
    assert (bdd / "CK3" / "Тест_english-russian.pdxtm").is_file()


def test_scan_dialog_finishes_without_hanging(tmp_path, make_tree, qtbot):
    from pdxloc import project
    from pdxloc.gui.scan_dialog import ScanProgressDialog

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.close()

    dlg = ScanProgressDialog(path, [])
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg.stats is not None or dlg.error is not None, timeout=15000)
    assert dlg.error is None
    assert dlg.stats.new == 2
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)


def test_scan_can_be_cancelled(tmp_path, make_tree, qtbot):
    from pdxloc import project
    from pdxloc.gui.scan_dialog import ScanProgressDialog

    en = make_tree({f"f{i}_l_english.yml": EN for i in range(40)}, "en")
    ru = make_tree({}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.close()

    dlg = ScanProgressDialog(path, [])
    qtbot.addWidget(dlg)
    dlg._on_cancel()
    qtbot.waitUntil(lambda: dlg.was_cancelled or dlg.stats is not None, timeout=15000)
    qtbot.waitUntil(lambda: not dlg._thread.isRunning(), timeout=5000)


def test_no_worker_signal_is_connected_to_a_lambda():
    """The signals of a background object go only to bound methods of the window.

    PySide calls a lambda directly in the thread of the sender, so such a binding
    imperceptibly takes work with widgets off into the worker thread.
    """
    import re
    from pathlib import Path

    gui = Path(__file__).resolve().parents[1] / "src" / "pdxloc" / "gui"
    bad = []
    for path in sorted(gui.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "moveToThread" not in text:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r"_worker\.\w+\.connect\(\s*lambda", line):
                bad.append(f"{path.name}:{n}: {line.strip()}")
    assert not bad, "сигнал рабочего потока подключён к лямбде:\n" + "\n".join(bad)


def test_qt_own_buttons_follow_the_interface_language(qtbot):
    """The standard buttons of Qt («Close», «Yes») are translated along with the interface.

    Our own translation and the one of Qt are set by one action: should they come
    apart, a Russian window would hold an English «Close» button — and the other
    way round.
    """
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from pdxloc.gui import language

    app = QApplication.instance()
    language.apply(app, "ru", save=False)
    box = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Ok)
    qtbot.addWidget(box)
    close_text = box.button(QDialogButtonBox.Close).text().replace("&", "")
    assert close_text == "Закрыть", f"кнопка осталась английской: {close_text}"

    language.apply(app, "en", save=False)
    box_en = QDialogButtonBox(QDialogButtonBox.Close)
    qtbot.addWidget(box_en)
    assert box_en.button(QDialogButtonBox.Close).text().replace("&", "") == "Close"

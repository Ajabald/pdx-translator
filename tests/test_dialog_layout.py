"""The layout of the modal windows.

A long label without wrapping stretches a window over the whole width of the
screen: the «Load a translation from a mod» window used to open 1764 pixels wide
because of one explanatory line. We check every window at once, so as not to catch
this by eye.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import tm  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'

# A label longer than this is a paragraph already, it needs wrapping.
LONG_LABEL = 60


@pytest.fixture
def conn(tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    c = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en, tgt_root=ru)
    scan_project(c, 1)
    tm.upsert(c, "Hello", "Привет")
    c.commit()
    yield c
    c.close()


def all_dialogs(conn):
    from pdxloc.gui.archive_dialog import ArchiveDialog
    from pdxloc.gui.concordance_dialog import ConcordanceDialog
    from pdxloc.gui.export_dialog import ExportDialog
    from pdxloc.gui.import_dialog import ImportDialog
    from pdxloc.gui.mt_dialog import MtDialog
    from pdxloc.gui.qa_panel import QaReportDialog
    from pdxloc.gui.root_dialog import EnRootDialog
    from pdxloc.gui.start_screen import ProjectDialog
    from pdxloc.gui.tm_window import TmWindow

    return {
        "Новый проект": ProjectDialog(),
        "Запись перевода в мод": ExportDialog(conn, 1),
        "Загрузить перевод из мода": ImportDialog(conn, 1),
        "Память переводов": TmWindow(conn),
        "Конкорданс": ConcordanceDialog(conn, "hello"),
        "Архив": ArchiveDialog(conn),
        "Отчёт проверки": QaReportDialog(conn, 1),
        "Смена папки оригинала": EnRootDialog(conn, 1),
        "Машинный перевод": MtDialog(conn, 1, None),
    }


def test_long_labels_wrap(conn, qtbot):
    from PySide6.QtWidgets import QLabel

    offenders = []
    for name, dlg in all_dialogs(conn).items():
        qtbot.addWidget(dlg)
        for label in dlg.findChildren(QLabel):
            text = label.text()
            if len(text) > LONG_LABEL and not label.wordWrap() and "<" not in text:
                offenders.append(f"{name}: {text[:70]}…")
    assert not offenders, "подписи без переноса:\n" + "\n".join(offenders)


def test_every_dialog_has_a_title(conn, qtbot):
    """A window without a title looks like somebody else's in the taskbar."""
    for name, dlg in all_dialogs(conn).items():
        qtbot.addWidget(dlg)
        assert dlg.windowTitle(), name


def test_browse_buttons_are_consistent(conn, qtbot):
    """The button that calls the explorer is labelled the same way in every window."""
    from PySide6.QtWidgets import QToolButton

    for name, dlg in all_dialogs(conn).items():
        qtbot.addWidget(dlg)
        for btn in dlg.findChildren(QToolButton):
            # without a label are the service buttons of Qt itself (the clear cross in a
            # search field); with a menu are drop-down lists, not a call of the explorer
            if not btn.text() or btn.menu() is not None:
                continue
            assert btn.text() == "Browse…", f"{name}: кнопка {btn.text()!r}"

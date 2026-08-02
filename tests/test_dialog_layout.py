"""Вёрстка модальных окон.

Длинная подпись без переноса растягивает окно на всю ширину экрана: окно
«Загрузить перевод из мода» так открывалось шириной 1764 пикселя из-за одной
поясняющей строки. Проверяем разом все окна, чтобы не ловить это глазами.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc import project, settings  # noqa: E402
from ck3loc.core import tm  # noqa: E402
from ck3loc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'

# Подпись длиннее этого — уже абзац, ей нужен перенос.
LONG_LABEL = 60


@pytest.fixture
def conn(tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    c = project.create_project(
        tmp_path / "p.ck3proj", name="P", src_root=en, tgt_root=ru)
    scan_project(c, 1)
    tm.upsert(c, "Hello", "Привет")
    c.commit()
    yield c
    c.close()


def all_dialogs(conn):
    from ck3loc.gui.archive_dialog import ArchiveDialog
    from ck3loc.gui.concordance_dialog import ConcordanceDialog
    from ck3loc.gui.export_dialog import ExportDialog
    from ck3loc.gui.import_dialog import ImportDialog
    from ck3loc.gui.qa_panel import QaReportDialog
    from ck3loc.gui.start_screen import ProjectDialog
    from ck3loc.gui.tm_import_dialog import TmImportDialog
    from ck3loc.gui.tm_manager_dialog import TmManagerDialog
    from ck3loc.gui.tm_sources_dialog import TmSourcesDialog

    return {
        "Новый проект": ProjectDialog(),
        "Создать базу переводов": TmImportDialog(),
        "Запись перевода в мод": ExportDialog(conn, 1),
        "Загрузить перевод из мода": ImportDialog(conn, 1),
        "Базы памяти переводов": TmSourcesDialog(conn),
        "Память переводов": TmManagerDialog(conn),
        "Конкорданс": ConcordanceDialog(conn, "hello"),
        "Архив": ArchiveDialog(conn),
        "Отчёт проверки": QaReportDialog(conn, 1),
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
    """Окно без заголовка в панели задач выглядит как чужое."""
    for name, dlg in all_dialogs(conn).items():
        qtbot.addWidget(dlg)
        assert dlg.windowTitle(), name


def test_browse_buttons_are_consistent(conn, qtbot):
    """Кнопка вызова проводника подписана одинаково во всех окнах."""
    from PySide6.QtWidgets import QToolButton

    for name, dlg in all_dialogs(conn).items():
        qtbot.addWidget(dlg)
        for btn in dlg.findChildren(QToolButton):
            # без подписи — служебные кнопки самого Qt (крестик очистки в поле
            # поиска); с меню — выпадающие списки, а не вызов проводника
            if not btn.text() or btn.menu() is not None:
                continue
            assert btn.text() == "Обзор…", f"{name}: кнопка {btn.text()!r}"

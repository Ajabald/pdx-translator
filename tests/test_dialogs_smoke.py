"""Каждый диалог должен хотя бы открываться.

Отдельный тест появился после того, как забытый импорт QPushButton уронил
диалог создания базы прямо в конструкторе: обычные тесты этого не ловили,
потому что до создания диалогов не доходили.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc import project  # noqa: E402
from ck3loc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def live_project(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    yield conn
    conn.close()


def test_tm_import_dialog_opens(qtbot):
    from ck3loc.gui.tm_import_dialog import TmImportDialog

    dlg = TmImportDialog()
    qtbot.addWidget(dlg)
    assert dlg.windowTitle()
    # кнопка прерывания появляется только во время работы
    assert not dlg.cancel_btn.isVisibleTo(dlg)


def test_tm_import_autodetects_typed_path(tmp_path, qtbot):
    """Путь можно вписать руками, а не только выбрать в проводнике."""
    from ck3loc.gui.tm_import_dialog import TmImportDialog

    loc = tmp_path / "Game" / "game" / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"m_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)

    dlg = TmImportDialog()
    qtbot.addWidget(dlg)
    dlg.src_edit.setText(str(tmp_path / "Game"))
    dlg._on_src_edited()

    assert dlg.src_edit.text() == str(loc / "english")
    assert dlg.tgt_edit.text() == str(loc / "russian")
    assert "с парой: 1" in dlg.status.text()


def test_tm_manager_dialog_opens(live_project, qtbot):
    from ck3loc.gui.tm_manager_dialog import TmManagerDialog

    dlg = TmManagerDialog(live_project)
    qtbot.addWidget(dlg)
    assert dlg.model.rowCount() >= 0


def test_tm_sources_dialog_opens(live_project, qtbot):
    from ck3loc.gui.tm_sources_dialog import TmSourcesDialog

    dlg = TmSourcesDialog(live_project)
    qtbot.addWidget(dlg)


def test_archive_dialog_opens(live_project, qtbot):
    from ck3loc.gui.archive_dialog import ArchiveDialog

    dlg = ArchiveDialog(live_project)
    qtbot.addWidget(dlg)


def test_export_dialog_opens(live_project, qtbot):
    from ck3loc.gui.export_dialog import ExportDialog

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert "l_russian" in dlg.preview.text()


def test_export_dialog_defaults_to_ru_root(live_project, qtbot, tmp_path):
    """Без прошлой записи цель — дерево перевода, и об этом честно сказано."""
    from ck3loc.gui.export_dialog import ExportDialog

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert dlg.path_edit.text() == str(tmp_path / "ru")
    assert dlg.warning.text()      # предупреждение о перезаписи источника импорта


def test_export_dialog_remembers_output_folder(live_project, qtbot, tmp_path):
    from ck3loc.gui.export_dialog import ExportDialog

    mod = tmp_path / "мод" / "localization"
    project.set_export_root(live_project, mod)
    project.set_last_export_at(live_project, "2026-08-02 01:47")

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert dlg.path_edit.text() == str(mod)
    assert not dlg.warning.text()   # это не папка импорта — предупреждать не о чем


def test_import_dialog_previews(live_project, qtbot, tmp_path):
    """Окно импорта сразу показывает, что именно изменится."""
    from ck3loc.gui.import_dialog import ImportDialog

    other = tmp_path / "other"
    other.mkdir()
    with open(other / "m_l_russian.yml", "w", encoding="utf-8-sig", newline="\n") as f:
        f.write('l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n')

    dlg = ImportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    dlg.path_edit.setText(str(other))
    dlg._preview()

    text = dlg.report_box.toPlainText()
    assert "Строк принято: 1" in text          # a уже переведено, b — новое
    assert "b: (пусто) → Мир" in text
    assert dlg.ok_button.isEnabled()

    dlg.overwrite.setChecked(True)             # предпросмотр пересчитывается сам
    assert "Строк принято: 2" in dlg.report_box.toPlainText()
    # ничего ещё не записано: предпросмотр только считает
    assert live_project.execute(
        "SELECT ru_text FROM units WHERE key = 'b'").fetchone()[0] is None


def test_concordance_dialog_finds_fragment(live_project, qtbot):
    from ck3loc.core import tm
    from ck3loc.gui.concordance_dialog import COL_RU, ConcordanceDialog

    tm.upsert(live_project, "Hello there", "Привет тебе")
    live_project.commit()

    dlg = ConcordanceDialog(live_project, "hello")
    qtbot.addWidget(dlg)

    # в памяти проекта уже лежит «Hello → Привет» из сканирования, плюс наша пара
    found = {dlg.table.item(i, COL_RU).text() for i in range(dlg.table.rowCount())}
    assert "Привет тебе" in found
    assert "Найдено:" in dlg.count_label.text()

    dlg.search.setText("нет такого фрагмента")
    dlg._reload()
    assert dlg.table.rowCount() == 0
    assert "Ничего не найдено" in dlg.count_label.text()


def test_suggestions_show_similarity_percent(live_project, qtbot):
    """Похожая строка видна в общем списке и подписана процентом."""
    from ck3loc.core import tm
    from ck3loc.gui.detail_pane import DetailPane

    tm.upsert(live_project, "Hello there", "Привет тебе")
    live_project.commit()
    unit_id = live_project.execute("SELECT id FROM units WHERE key = 'b'").fetchone()[0]
    live_project.execute("UPDATE units SET en_text = 'Hello here' WHERE id = ?", (unit_id,))
    live_project.commit()

    pane = DetailPane(live_project)
    qtbot.addWidget(pane)
    pane.load_unit(unit_id)

    texts = [pane.tm_list.item(i).text() for i in range(pane.tm_list.count())]
    assert any("Привет тебе" in t and "%" in t for t in texts), texts


def test_nbsp_survives_the_editor(live_project, qtbot):
    """Неразрывный пробел не должен подменяться обычным.

    В русской типографике он стоит осмысленно (перед тире, в «5 000»), и в
    ванильной локализации CK3 таких строк полно. Qt в toPlainText() меняет его
    на обычный: строка, которую даже не открывали для правки, считалась
    изменённой и перезаписывалась при уходе с неё.
    """
    from ck3loc.gui.detail_pane import DetailPane

    text = "Стариков — я позабочусь о них"
    unit_id = live_project.execute("SELECT id FROM units WHERE key = 'a'").fetchone()[0]
    live_project.execute("UPDATE units SET ru_text = ? WHERE id = ?", (text, unit_id))
    live_project.commit()

    pane = DetailPane(live_project)
    qtbot.addWidget(pane)
    pane.load_unit(unit_id)

    assert pane.ru_edit.toPlainText() != text          # Qt действительно подменяет
    assert "сохранено" in pane.save_state.text()       # но правок-то не было
    pane._autosave()
    assert live_project.execute(
        "SELECT ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()[0] == text


def test_qa_report_dialog_opens(live_project, qtbot):
    from ck3loc.gui.qa_panel import QaReportDialog

    dlg = QaReportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert "проблем" in dlg.count_label.text()


def test_scan_summary_dialog_opens(qtbot):
    from ck3loc.core.models import ScanStats
    from ck3loc.gui.scan_dialog import ScanSummaryDialog

    stats = ScanStats(files_en=3, new=5, stale=2, changed_cosmetic=1, changed_meaningful=1)
    dlg = ScanSummaryDialog(stats)
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == len(ScanSummaryDialog.ROWS)


def test_project_dialog_opens(qtbot):
    from ck3loc.gui.start_screen import ProjectDialog

    dlg = ProjectDialog()
    qtbot.addWidget(dlg)
    assert dlg.src_lang.currentText() == "english"


def test_main_window_opens(qtbot, monkeypatch, tmp_path):
    from ck3loc import settings

    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    # иначе окно попытается перенести настоящую базу прежней версии
    # и покажет модальное сообщение, которое в тестах некому закрыть
    monkeypatch.setattr(settings, "default_db_path", lambda: tmp_path / "нет-такой.sqlite3")

    from ck3loc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    assert win.windowTitle()

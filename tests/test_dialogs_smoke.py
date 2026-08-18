"""Каждый диалог должен хотя бы открываться.

Отдельный тест появился после того, как забытый импорт QPushButton уронил
диалог создания базы прямо в конструкторе: обычные тесты этого не ловили,
потому что до создания диалогов не доходили.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def live_project(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    yield conn
    conn.close()


def test_tm_import_dialog_opens(qtbot):
    from pdxloc.gui.tm_build_tab import TmBuildTab

    tab = TmBuildTab()
    qtbot.addWidget(tab)
    # кнопка прерывания появляется только во время работы
    assert not tab.cancel_btn.isVisibleTo(tab)


def test_tm_import_autodetects_typed_path(tmp_path, qtbot):
    """Путь можно вписать руками, а не только выбрать в проводнике."""
    from pdxloc.gui.tm_build_tab import TmBuildTab

    loc = tmp_path / "Game" / "game" / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"m_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)

    tab = TmBuildTab()
    qtbot.addWidget(tab)
    tab.src_edit.setText(str(tmp_path / "Game"))
    tab._on_src_edited()

    assert tab.src_edit.text() == str(loc / "english")
    assert tab.tgt_edit.text() == str(loc / "russian")
    assert "with a pair: 1" in tab.status.text()


def test_tm_window_opens_with_all_tabs(live_project, qtbot):
    from pdxloc.gui.tm_window import TmWindow

    win = TmWindow(live_project)
    qtbot.addWidget(win)
    assert win.tabs.count() == 3
    assert win.entries.model.rowCount() >= 0
    assert win.sources.list is not None


def test_glossary_window_opens_with_both_tabs(live_project, qtbot, tmp_path):
    from pdxloc.gui.glossary_window import GlossaryWindow

    win = GlossaryWindow(live_project, tmp_path / "p.pdxproj")
    qtbot.addWidget(win)
    assert win.tabs.count() == 2
    assert win.terms.model.rowCount() == 0
    assert win.candidates.model.rowCount() == 0
    win.terms.shutdown()
    win.candidates.shutdown()


def test_archive_dialog_opens(live_project, qtbot):
    from pdxloc.gui.archive_dialog import ArchiveDialog

    dlg = ArchiveDialog(live_project)
    qtbot.addWidget(dlg)


def test_export_dialog_opens(live_project, qtbot):
    from pdxloc.gui.export_dialog import ExportDialog

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert "l_russian" in dlg.preview.text()


def test_export_dialog_defaults_to_ru_root(live_project, qtbot, tmp_path):
    """Без прошлой записи цель — дерево перевода, и об этом честно сказано."""
    from pdxloc.gui.export_dialog import ExportDialog

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert dlg.path_edit.text() == str(tmp_path / "ru")
    assert dlg.warning.text()      # предупреждение о перезаписи источника импорта


def test_export_dialog_remembers_output_folder(live_project, qtbot, tmp_path):
    from pdxloc.gui.export_dialog import ExportDialog

    mod = tmp_path / "мод" / "localization"
    project.set_export_root(live_project, mod)
    project.set_last_export_at(live_project, "2026-08-02 01:47")

    dlg = ExportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert dlg.path_edit.text() == str(mod)
    assert not dlg.warning.text()   # это не папка импорта — предупреждать не о чем


def test_import_dialog_previews(live_project, qtbot, tmp_path):
    """Окно импорта сразу показывает, что именно изменится."""
    from pdxloc.gui.import_dialog import ImportDialog

    other = tmp_path / "other"
    other.mkdir()
    with open(other / "m_l_russian.yml", "w", encoding="utf-8-sig", newline="\n") as f:
        f.write('l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n')

    dlg = ImportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    dlg.path_edit.setText(str(other))
    dlg._reread()                              # смена папки — единственное чтение диска

    text = dlg.report_box.toPlainText()
    assert "Rows taken: 1" in text          # a уже переведено, b — новое
    assert "b: (empty) → Мир" in text
    assert dlg.ok_button.isEnabled()

    # Галка меняет правила приёма, а не файлы на диске: пересчёт идёт по уже
    # разобранному дереву. Раньше каждое переключение обходило весь мод заново.
    from pdxloc.core import paradox_yaml

    reads: list = []
    real = paradox_yaml.parse_file
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(paradox_yaml, "parse_file",
                        lambda p: (reads.append(p), real(p))[1])
    try:
        dlg.overwrite.setChecked(True)         # предпросмотр пересчитывается сам
        assert "Rows taken: 2" in dlg.report_box.toPlainText()
        assert reads == [], "диск читали заново ради галки"
    finally:
        monkeypatch.undo()

    # ничего ещё не записано: предпросмотр только считает
    assert live_project.execute(
        "SELECT ru_text FROM units WHERE key = 'b'").fetchone()[0] is None


def test_concordance_dialog_finds_fragment(live_project, qtbot):
    from pdxloc.core import tm
    from pdxloc.gui.concordance_dialog import COL_RU, ConcordanceDialog

    tm.upsert(live_project, "Hello there", "Привет тебе")
    live_project.commit()

    dlg = ConcordanceDialog(live_project, "hello")
    qtbot.addWidget(dlg)

    # в памяти проекта уже лежит «Hello → Привет» из сканирования, плюс наша пара
    found = {dlg.table.item(i, COL_RU).text() for i in range(dlg.table.rowCount())}
    assert "Привет тебе" in found
    assert "Found:" in dlg.count_label.text()

    dlg.search.setText("нет такого фрагмента")
    dlg._reload()
    assert dlg.table.rowCount() == 0
    assert "Nothing found" in dlg.count_label.text()


def test_suggestions_show_similarity_percent(live_project, qtbot):
    """Похожая строка видна в общем списке и подписана процентом."""
    from pdxloc.core import tm
    from pdxloc.gui.detail_pane import DetailPane

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
    from pdxloc.gui.detail_pane import DetailPane

    text = "Стариков — я позабочусь о них"
    unit_id = live_project.execute("SELECT id FROM units WHERE key = 'a'").fetchone()[0]
    live_project.execute("UPDATE units SET ru_text = ? WHERE id = ?", (text, unit_id))
    live_project.commit()

    pane = DetailPane(live_project)
    qtbot.addWidget(pane)
    pane.load_unit(unit_id)

    assert pane.ru_edit.toPlainText() != text          # Qt действительно подменяет
    assert "saved" in pane.save_state.text()           # но правок-то не было
    pane._autosave()
    assert live_project.execute(
        "SELECT ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()[0] == text


def test_qa_report_dialog_opens(live_project, qtbot):
    from pdxloc.gui.qa_panel import QaReportDialog

    dlg = QaReportDialog(live_project, 1)
    qtbot.addWidget(dlg)
    assert "issues" in dlg.count_label.text()


def test_rules_window_opens(live_project, qtbot):
    from pdxloc.gui.rules_window import RulesWindow

    dlg = RulesWindow(live_project)
    qtbot.addWidget(dlg)
    try:
        assert dlg.tabs.count() == 2
        assert dlg.rules_tab.tree.topLevelItemCount() > 0
    finally:
        dlg.rules_tab.shutdown()


def test_scan_summary_dialog_opens(qtbot):
    from pdxloc.core.models import ScanStats
    from pdxloc.gui.scan_dialog import ScanSummaryDialog

    stats = ScanStats(files_en=3, new=5, stale=2, changed_cosmetic=1, changed_meaningful=1)
    dlg = ScanSummaryDialog(stats)
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == len(ScanSummaryDialog.ROWS)


def test_project_dialog_opens(qtbot):
    from pdxloc.gui.start_screen import ProjectDialog

    dlg = ProjectDialog()
    qtbot.addWidget(dlg)
    assert dlg.src_lang.currentText() == "english"


def test_main_window_opens(qtbot, monkeypatch, tmp_path):
    from pdxloc import settings

    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    # иначе окно попытается перенести настоящую базу прежней версии
    # и покажет модальное сообщение, которое в тестах некому закрыть

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    assert win.windowTitle()

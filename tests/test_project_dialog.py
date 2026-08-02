"""Окно «Новый проект»: предзаполнение путей и создание проекта."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc import project, settings  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n'


@pytest.fixture
def dialog(tmp_path, monkeypatch, qtbot):
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "last_browse_dir", lambda: "")
    monkeypatch.setattr(settings, "set_last_browse_dir", lambda p: None)

    from ck3loc.gui.start_screen import ProjectDialog

    dlg = ProjectDialog()
    qtbot.addWidget(dlg)
    return dlg


def test_project_file_defaults_to_projects_dir(dialog, tmp_path):
    """Папка по умолчанию — Projects внутри приложения, но путь виден и правится."""
    assert str(tmp_path / "Projects") in dialog.file_edit.placeholderText()

    dialog.name_edit.setText("Мой мод")

    assert dialog.file_edit.text() == str(tmp_path / "Projects" / "Мой мод.ck3proj")


def test_name_with_forbidden_characters(dialog, tmp_path):
    dialog.name_edit.setText("Bloodlines: Legacies/AGOT")
    assert dialog.file_edit.text() == str(
        tmp_path / "Projects" / "Bloodlines_ Legacies_AGOT.ck3proj")


def test_bare_file_name_goes_to_projects_dir(dialog, tmp_path):
    """Ввели просто имя — файл всё равно должен лечь в папку проектов."""
    dialog.name_edit.setText("Мод")
    dialog.file_edit.setText("другое-имя")

    assert dialog.values()["path"] == tmp_path / "Projects" / "другое-имя.ck3proj"


def test_target_folder_suggested_from_source(dialog, tmp_path):
    """Указали …\\localization\\english — папка перевода предлагается сама."""
    src = tmp_path / "mod" / "localization" / "english"
    dialog.src_edit.setText(str(src))
    dialog._suggest_target()

    assert dialog.tgt_edit.text() == str(tmp_path / "mod" / "localization" / "russian")


def test_target_suggestion_follows_language(dialog, tmp_path):
    dialog.tgt_lang.setCurrentText("french")
    dialog.src_edit.setText(str(tmp_path / "loc" / "english"))
    dialog._suggest_target()

    assert dialog.tgt_edit.text().endswith("french")


def test_target_not_overwritten(dialog, tmp_path):
    dialog.tgt_edit.setText(str(tmp_path / "своя папка"))
    dialog.src_edit.setText(str(tmp_path / "loc" / "english"))
    dialog._suggest_target()

    assert dialog.tgt_edit.text() == str(tmp_path / "своя папка")


def test_browse_buttons_are_labelled(dialog):
    """Кнопки проводника подписаны, как в остальных окнах, а не узкое «…»."""
    from PySide6.QtWidgets import QToolButton

    labels = {b.text() for b in dialog.findChildren(QToolButton)}
    assert labels == {"Обзор…"}


def test_creates_working_project(dialog, tmp_path, make_tree):
    """Сквозная проверка: заполнили окно — получили рабочий файл проекта."""
    from ck3loc.core.scanner import scan_project

    src = make_tree({"m_l_english.yml": EN}, "en")
    dialog.name_edit.setText("Проверка")
    dialog.src_edit.setText(str(src))
    dialog._suggest_target()
    values = dialog.values()

    conn = project.create_project(
        values["path"], name=values["name"], src_root=values["src_root"],
        tgt_root=values["tgt_root"], src_lang=values["src_lang"],
        tgt_lang=values["tgt_lang"])
    try:
        stats = scan_project(conn, 1)
        assert stats.new == 1
        assert project.project_name(conn) == "Проверка"
        row = conn.execute("SELECT src_lang, tgt_lang FROM projects").fetchone()
        assert (row["src_lang"], row["tgt_lang"]) == ("english", "russian")
    finally:
        conn.close()
    assert values["path"].is_file()
    assert values["path"].parent == tmp_path / "Projects"

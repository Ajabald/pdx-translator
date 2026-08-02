"""Главное окно: стек экранов, меню, статус-бар."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMainWindow, QMessageBox, QStackedWidget,
)

from ck3loc import project, settings
from ck3loc.core import unit_ops
from ck3loc.core.statuses import Status
from ck3loc.core.stats import format_status_bar, project_stats
from ck3loc.gui import theme
from ck3loc.gui.editor_screen import EditorScreen
from ck3loc.gui.scan_dialog import ScanProgressDialog, ScanSummaryDialog
from ck3loc.gui.start_screen import StartScreen
from ck3loc.gui.status_chips import StatusChipsBar
from ck3loc.gui.toolbar import ContextBar, build_toolbar

PROJECT_ID = 1      # в файле проекта всегда ровно один проект


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CK3 Translator")
        settings.ensure_dirs()
        self.conn = None
        self.project_path: Path | None = None

        self.stack = QStackedWidget()
        self.start_screen = StartScreen()
        self.editor_screen = EditorScreen()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.editor_screen)
        self.setCentralWidget(self.stack)

        self.start_screen.projectOpened.connect(lambda p: self.open_project(Path(p)))
        self.editor_screen.statsChanged.connect(self._update_status_bar)
        self.editor_screen.manageTmRequested.connect(self._tm_manager)
        self.editor_screen.selectionChanged.connect(self._on_selection_changed)

        # Постоянные виджеты: временные сообщения (showMessage) их не перекрывают,
        # иначе счётчик пропадал бы после каждого уведомления
        self.selection_label = QLabel()
        self.statusBar().addPermanentWidget(self.selection_label)
        self.stats_label = QLabel()
        self.statusBar().addPermanentWidget(self.stats_label)
        self.chips = StatusChipsBar()
        self.chips.chipClicked.connect(self._on_chip_filter)
        self.statusBar().addPermanentWidget(self.chips)
        self.chips.hide()

        self.context_bar = ContextBar()
        self.context_bar.tmSourcesChanged.connect(self.editor_screen.refresh_current)
        self._build_menu()
        self.toolbar = build_toolbar(self)
        self.addToolBar(self.toolbar)
        self._restore_view_settings()
        self._restore_geometry()
        self.statusBar().showMessage("Выберите или создайте проект")

        self._migrate_legacy()
        last = settings.last_project_path()
        if last and last.is_file():
            self.open_project(last)

    # --- перенос базы прежних версий ---

    def _migrate_legacy(self) -> None:
        try:
            created = project.migrate_legacy_if_needed()
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(
                self, "Перенос данных",
                f"Не удалось перенести базу прежней версии:\n{e}\n\n"
                "Старый файл не изменён — сообщите об ошибке.")
            return
        if created:
            paths = "\n".join(str(p) for p in created)
            QMessageBox.information(
                self, "Перенос данных",
                f"Проекты перенесены в отдельные файлы:\n\n{paths}\n\n"
                "Прежняя база сохранена рядом с расширением .migrated.")
            self.start_screen.reload()

    # --- меню ---

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&Файл")
        act_projects = QAction("Проекты", self)
        act_projects.triggered.connect(self.show_start)
        m_file.addAction(act_projects)
        act_open = QAction("Открыть проект…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self._open_file)
        m_file.addAction(act_open)
        self.act_save_as = QAction("Сохранить проект как…", self)
        self.act_save_as.triggered.connect(self._save_as)
        m_file.addAction(self.act_save_as)
        m_file.addSeparator()
        act_exit = QAction("Выход", self)
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        m_project = self.menuBar().addMenu("&Проект")
        self.act_scan = QAction("Сканировать", self)
        self.act_scan.setShortcut(QKeySequence("F5"))
        self.act_scan.triggered.connect(self.scan_current)
        m_project.addAction(self.act_scan)
        self.act_qa = QAction("Проверить весь проект…", self)
        self.act_qa.setShortcut(QKeySequence("F6"))
        self.act_qa.triggered.connect(self._show_qa)
        m_project.addAction(self.act_qa)
        self.act_actualize_cosmetic = QAction("Актуализировать косметические правки…", self)
        self.act_actualize_cosmetic.setToolTip(
            "Подтвердить переводы строк, где автор мода правил только оформление")
        self.act_actualize_cosmetic.triggered.connect(self._actualize_cosmetic)
        m_project.addAction(self.act_actualize_cosmetic)
        self.act_undo = QAction("Отменить последнюю операцию", self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_undo.triggered.connect(self._undo_last)
        m_project.addAction(self.act_undo)
        m_project.addSeparator()
        self.act_import = QAction("Загрузить перевод из мода…", self)
        self.act_import.setToolTip(
            "Принять переводы из готовых файлов локализации — чужой перевод "
            "этого мода или свои правки, сделанные прямо в файлах")
        self.act_import.triggered.connect(self._import_translations)
        m_project.addAction(self.act_import)
        self.act_archive = QAction("Архив старых переводов…", self)
        self.act_archive.triggered.connect(self._show_archive)
        m_project.addAction(self.act_archive)
        self.act_export = QAction("Записать перевод в мод…", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export.triggered.connect(self._export)
        m_project.addAction(self.act_export)

        # Действия без своих клавиш: те же операции уже висят на F7…F10 в
        # таблице, а второй хоткей на то же действие Qt считает конфликтом.
        self.act_find = QAction("Поиск по строкам", self)
        self.act_find.setToolTip("Курсор в поле поиска (Ctrl+F)")
        self.act_find.triggered.connect(lambda: self.editor_screen.focus_search())
        self.act_next_untranslated = QAction("Следующая непереведённая", self)
        self.act_next_untranslated.triggered.connect(
            lambda: self.editor_screen.goto_next_untranslated())
        self.act_validate = QAction("Подтвердить выделенные", self)
        self.act_validate.setToolTip("Пометить выделенные строки проверенными (F10)")
        self.act_validate.triggered.connect(
            lambda: self.editor_screen.set_status_of_selection(Status.REVIEWED))
        self.act_unvalidate = QAction("Снять подтверждение", self)
        self.act_unvalidate.setToolTip("Вернуть статус «Переведено» (Shift+F10)")
        self.act_unvalidate.triggered.connect(
            lambda: self.editor_screen.set_status_of_selection(Status.TRANSLATED))

        m_view = self.menuBar().addMenu("&Вид")
        self.act_show_toolbar = QAction("Панель инструментов", self, checkable=True)
        self.act_show_toolbar.toggled.connect(self._toggle_toolbar)
        m_view.addAction(self.act_show_toolbar)
        self.act_show_tree = QAction("Дерево файлов", self, checkable=True)
        self.act_show_tree.toggled.connect(self._toggle_tree)
        m_view.addAction(self.act_show_tree)
        self.act_show_context = QAction("Языки и базы в шапке", self, checkable=True)
        self.act_show_context.toggled.connect(self._toggle_context)
        m_view.addAction(self.act_show_context)
        m_view.addSeparator()
        theme_menu = m_view.addMenu("Тема")
        group = QActionGroup(self)
        self.theme_actions = {}
        for name, label in theme.THEME_LABELS.items():
            act = QAction(label, self, checkable=True)
            act.setChecked(theme.current() == name)
            act.triggered.connect(lambda _, n=name: self._set_theme(n))
            group.addAction(act)
            theme_menu.addAction(act)
            self.theme_actions[name] = act

        m_tools = self.menuBar().addMenu("&Инструменты")
        self.act_tm_manager = QAction("Память переводов…", self)
        self.act_tm_manager.setShortcut(QKeySequence("F9"))
        self.act_tm_manager.triggered.connect(self._tm_manager)
        m_tools.addAction(self.act_tm_manager)
        self.act_tm_sources = QAction("Базы памяти переводов…", self)
        self.act_tm_sources.triggered.connect(self._tm_sources)
        m_tools.addAction(self.act_tm_sources)
        act_tm_build = QAction("Создать базу переводов из папок…", self)
        act_tm_build.triggered.connect(self._tm_build)
        m_tools.addAction(act_tm_build)
        self.act_tm_export = QAction("Выгрузить переводы проекта в базу…", self)
        self.act_tm_export.triggered.connect(self._tm_export)
        m_tools.addAction(self.act_tm_export)
        m_tools.addSeparator()
        act_open_bdd = QAction("Открыть папку баз", self)
        act_open_bdd.triggered.connect(self._open_bdd_dir)
        m_tools.addAction(act_open_bdd)
        self.act_mt = QAction("Машинный перевод… (в разработке)", self)
        self.act_mt.setEnabled(False)
        m_tools.addAction(self.act_mt)

        m_help = self.menuBar().addMenu("&Справка")
        act_keys = QAction("Горячие клавиши", self)
        act_keys.triggered.connect(self._show_shortcuts)
        m_help.addAction(act_keys)
        act_about = QAction("О программе", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

        self._set_project_actions(False)

    def _set_project_actions(self, enabled: bool) -> None:
        for a in (self.act_scan, self.act_qa, self.act_export, self.act_archive,
                  self.act_save_as, self.act_tm_sources, self.act_tm_export,
                  self.act_tm_manager, self.act_actualize_cosmetic, self.act_undo,
                  self.act_find, self.act_next_untranslated, self.act_import,
                  self.act_validate, self.act_unvalidate):
            a.setEnabled(enabled)

    # --- вид ---

    def _restore_view_settings(self) -> None:
        s = settings.qsettings()
        self.act_show_toolbar.setChecked(s.value("view/toolbar", True, type=bool))
        self.act_show_tree.setChecked(s.value("view/file_tree", True, type=bool))
        self.act_show_context.setChecked(s.value("view/context", True, type=bool))

    def _toggle_toolbar(self, visible: bool) -> None:
        self.toolbar.setVisible(visible)
        settings.qsettings().setValue("view/toolbar", visible)

    def _toggle_tree(self, visible: bool) -> None:
        self.editor_screen.file_tree.setVisible(visible)
        settings.qsettings().setValue("view/file_tree", visible)

    def _toggle_context(self, visible: bool) -> None:
        self.context_bar.setVisible(visible)
        settings.qsettings().setValue("view/context", visible)

    def _set_theme(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication

        theme.apply_theme(QApplication.instance(), name)

    def _show_shortcuts(self) -> None:
        """Один список клавиш — раскладка та же, что у ESP/ESM Translator."""
        rows = [
            ("F5", "Сканировать проект"),
            ("F6", "Проверить весь проект"),
            ("F7", "Подставить из памяти переводов"),
            ("F8", "Перевод = Оригинал"),
            ("F9", "Память переводов"),
            ("F10 / Shift+F10", "Подтвердить / снять подтверждение"),
            ("Ctrl+F10 / Ctrl+Shift+F10", "Кастомный статус / игнорировать"),
            ("Ctrl+F6", "Применить ко всем строкам с тем же оригиналом"),
            ("Ctrl+E", "Записать перевод в мод"),
            ("Ctrl+F", "Поиск по строкам"),
            ("Ctrl+Z", "Отменить последнюю операцию"),
            ("Ctrl+S", "Сохранить перевод (панель редактора)"),
            ("Ctrl+Enter", "Сохранить и перейти к следующей непереведённой"),
            ("Ctrl+↑ / Ctrl+↓", "Предыдущая / следующая строка"),
            ("F2, двойной клик", "Править перевод прямо в ячейке"),
        ]
        body = "".join(f"<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{v}</td></tr>"
                       for k, v in rows)
        QMessageBox.information(
            self, "Горячие клавиши", f"<table>{body}</table>")

    # --- проекты ---

    def show_start(self) -> None:
        self.start_screen.reload()
        self.stack.setCurrentWidget(self.start_screen)

    def open_project(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            QMessageBox.warning(self, "Проект", f"Файл проекта не найден:\n{path}")
            return
        try:
            conn = project.open_project(path)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(self, "Проект", f"Не удалось открыть проект:\n{e}")
            return

        self._close_project()
        self.conn = conn
        self.project_path = path
        name = project.project_name(conn)
        self.setWindowTitle(f"{name} — CK3 Translator")
        conn.execute("UPDATE projects SET last_opened_at = datetime('now') WHERE id = 1")
        conn.commit()
        settings.set_last_project_path(path)

        has_units = conn.execute("SELECT 1 FROM units LIMIT 1").fetchone()
        self.editor_screen.set_session(conn)
        if not has_units:
            self.scan_current()
        # строки, где переводить нечего (одна разметка), не должны висеть
        # в непереведённых — в том числе в проектах прежних версий
        auto_ignored = unit_ops.auto_ignore_untranslated(conn, PROJECT_ID)
        self.editor_screen.open_project(PROJECT_ID)
        self.stack.setCurrentWidget(self.editor_screen)
        self._set_project_actions(True)
        self.context_bar.set_project(conn)
        self.editor_screen.file_tree.setVisible(self.act_show_tree.isChecked())
        self._update_status_bar()
        self.statusBar().clearMessage()      # убрать приглашение выбрать проект
        if auto_ignored:
            self.statusBar().showMessage(
                f"{auto_ignored} строк без переводимого текста помечены как "
                f"игнорируемые (только теги вроде [GetName])", 8000)

    def _close_project(self) -> None:
        if self.conn is not None:
            self.editor_screen.close_session()
            stats = project_stats(self.conn, PROJECT_ID)
            settings.remember_project(
                self.project_path, project.project_name(self.conn), stats.done, stats.total)
            self.conn.close()
            self.conn = None
        # действия проекта без проекта только сбивают с толку: раньше они
        # оставались включёнными и падали на пустом соединении
        self._set_project_actions(False)
        self.context_bar.set_project(None)
        self.chips.hide()
        self.stats_label.clear()
        self.selection_label.clear()

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть проект", str(settings.projects_dir()),
            f"Проект перевода (*{settings.PROJECT_EXT});;Все файлы (*)")
        if path:
            self.open_project(Path(path))

    def _save_as(self) -> None:
        if self.conn is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить проект как", str(settings.projects_dir()),
            f"Проект перевода (*{settings.PROJECT_EXT})")
        if not path:
            return
        target = Path(path)
        if target == self.project_path:
            return
        target.unlink(missing_ok=True)
        try:
            project.save_project_as(self.conn, target)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить:\n{e}")
            return
        QMessageBox.information(
            self, "Сохранение", f"Проект сохранён:\n{target}\n\nОткрываю копию.")
        self.open_project(target)

    def scan_current(self) -> None:
        if self.project_path is None:
            return
        tm_paths = project.project_tm_paths(self.conn) if self.conn else []
        dlg = ScanProgressDialog(self.project_path, tm_paths, self)
        if dlg.exec() and dlg.stats is not None:
            summary = ScanSummaryDialog(dlg.stats, self)
            summary.showRequested.connect(self.editor_screen.set_status_filter)
            summary.exec()
        elif dlg.was_cancelled:
            self.statusBar().showMessage(
                "Сканирование прервано — изменения не сохранены", 6000)
        elif dlg.error:
            QMessageBox.critical(self, "Сканирование", f"Ошибка:\n{dlg.error}")
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    # --- сервис ---

    def _update_status_bar(self) -> None:
        if self.conn is None:
            return
        stats = project_stats(self.conn, PROJECT_ID)
        self.stats_label.setText(format_status_bar(stats))
        self.chips.set_stats(stats)
        self.chips.show()

    def _on_selection_changed(self, count: int) -> None:
        """Охват массовой операции виден до нажатия, а не после."""
        self.selection_label.setText(f"Выбрано строк: {count}" if count > 1 else "")

    def _on_chip_filter(self, status_value: str) -> None:
        self.editor_screen.set_status_filter(status_value or None)

    def _show_qa(self) -> None:
        """Полная проверка проекта отдельным отчётом.

        Повседневные замечания видны в колонке «!» таблицы, поэтому панель
        больше не занимает место на экране постоянно.
        """
        from ck3loc.gui.qa_panel import QaReportDialog

        if self.conn is None:
            return
        dlg = QaReportDialog(self.conn, PROJECT_ID, self)
        dlg.jumpToUnit.connect(self.editor_screen.jump_to_unit)
        dlg.exec()
        self.editor_screen.refresh_issues()

    def _actualize_cosmetic(self) -> None:
        """Подтвердить переводы строк, где автор мода правил только оформление."""
        if self.conn is None:
            return
        ids = unit_ops.cosmetic_stale_ids(self.conn, PROJECT_ID)
        if not ids:
            QMessageBox.information(
                self, "Косметические правки",
                "Устаревших строк с косметическими правками нет.\n\n"
                "Такими считаются изменения пунктуации, регистра и пробелов — "
                "когда смысл оригинала не поменялся.")
            return
        answer = QMessageBox.question(
            self, "Косметические правки",
            f"Подтвердить переводы {len(ids)} строк, где оригинал правили только "
            f"косметически?\n\nСами переводы не изменятся — снимется пометка "
            f"«Устарело». Операцию можно отменить (Ctrl+Z).")
        if answer != QMessageBox.Yes:
            return
        batch = unit_ops.new_batch_id()
        changed = unit_ops.actualize(self.conn, ids, batch_id=batch)
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()
        self.statusBar().showMessage(f"Актуализировано строк: {changed}", 6000)

    def _undo_last(self) -> None:
        if self.conn is None:
            return
        info = unit_ops.last_batch(self.conn)
        if info is None:
            QMessageBox.information(self, "Отмена", "Отменять нечего.")
            return
        batch_id, origin, count = info
        labels = {"actualize": "актуализация", "bulk": "смена статуса",
                  "manual": "правка перевода", "replace": "замена",
                  "glossary": "правила глоссария", "tm": "подстановка из памяти",
                  "import": "загрузка перевода из мода"}
        answer = QMessageBox.question(
            self, "Отмена операции",
            f"Отменить последнюю операцию ({labels.get(origin, origin)}) "
            f"и вернуть {count} строк к прежнему состоянию?")
        if answer != QMessageBox.Yes:
            return
        restored = unit_ops.undo_batch(self.conn, batch_id)
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()
        self.statusBar().showMessage(f"Возвращено строк: {restored}", 6000)

    def _tm_manager(self) -> None:
        from ck3loc.gui.tm_manager_dialog import TmManagerDialog

        if self.conn is None:
            return
        TmManagerDialog(self.conn, self).exec()
        self.editor_screen.refresh_current()

    def _tm_sources(self) -> None:
        from ck3loc.gui.tm_sources_dialog import TmSourcesDialog

        if self.conn is None:
            return
        if TmSourcesDialog(self.conn, self).exec():
            self.editor_screen.refresh_current()
            self.context_bar.refresh()

    def _tm_build(self) -> None:
        from ck3loc.gui.tm_import_dialog import TmImportDialog

        src_lang, tgt_lang = "english", "russian"
        if self.conn is not None:
            row = self.conn.execute(
                "SELECT src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
            if row:
                src_lang, tgt_lang = row["src_lang"], row["tgt_lang"]
        TmImportDialog(self, src_lang=src_lang, tgt_lang=tgt_lang).exec()
        self.context_bar.refresh()      # новая база должна появиться в списке

    def _tm_export(self) -> None:
        from ck3loc.core import tm_import

        if self.conn is None:
            return
        name = project.project_name(self.conn)
        safe = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .")
        row = self.conn.execute(
            "SELECT src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
        default = settings.bdd_dir() / \
            f"{safe}_{row['src_lang']}-{row['tgt_lang']}{settings.TM_EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Выгрузить переводы проекта", str(default),
            f"База переводов (*{settings.TM_EXT})")
        if not path:
            return
        try:
            report = tm_import.export_project_tm(self.conn, Path(path), name=name)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(self, "Выгрузка", f"Не удалось выгрузить:\n{e}")
            return
        QMessageBox.information(
            self, "Выгрузка",
            f"Готово: {report.pairs} пар переводов.\n\n{path}")

    def _open_bdd_dir(self) -> None:
        import subprocess

        settings.bdd_dir().mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(settings.bdd_dir())])

    def _show_archive(self) -> None:
        from ck3loc.gui.archive_dialog import ArchiveDialog

        ArchiveDialog(self.conn, self).exec()

    def _export(self) -> None:
        from ck3loc.gui.export_dialog import ExportDialog

        if self.conn is not None:
            ExportDialog(self.conn, PROJECT_ID, self).exec()

    def _import_translations(self) -> None:
        from ck3loc.gui.import_dialog import ImportDialog

        if self.conn is None:
            return
        dlg = ImportDialog(self.conn, PROJECT_ID, self)
        dlg.imported.connect(self._after_import)
        dlg.exec()

    def _after_import(self) -> None:
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    def _about(self) -> None:
        from ck3loc import __version__

        where = self.project_path or "(проект не открыт)"
        QMessageBox.about(
            self, "CK3 Translator",
            f"<b>CK3 Translator</b> v{__version__}<br><br>"
            "Переводчик локализаций модов Crusader Kings 3.<br>"
            "Формат: Paradox pseudo-YAML (UTF-8 c BOM).<br><br>"
            f"Проект: {where}<br>Базы памяти: {settings.bdd_dir()}")

    # --- геометрия ---

    def _restore_geometry(self) -> None:
        geo = settings.qsettings().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 800)

    def closeEvent(self, event) -> None:
        settings.qsettings().setValue("geometry", self.saveGeometry())
        self._close_project()
        super().closeEvent(event)

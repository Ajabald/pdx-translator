"""The main window: the stack of screens, the menu, the status bar."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QLabel, QMainWindow, QMessageBox, QStackedWidget,
)

from pdxloc import project, settings
from pdxloc.core import (
    games, qa_rules, statuses as statuses_mod, trash, unit_ops,
)
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.statuses import STATUS_ORDER
from pdxloc.core.stats import format_status_bar, project_stats
from pdxloc.gui import actions as act_spec, language, prefs, rules_state, shell, theme
from pdxloc.gui.actions import ACTIONS, MENU, SEP, ActionRegistry
from pdxloc.gui.units_model import DATA_COLUMNS, SORT_COLUMNS
from pdxloc.gui.editor_screen import EditorScreen
from pdxloc.gui.scan_dialog import ScanProgressDialog, ScanSummaryDialog
from pdxloc.gui.start_screen import StartScreen
from pdxloc.gui.status_chips import StatusChipsBar
from pdxloc.gui.toolbar import ContextBar, build_toolbar

PROJECT_ID = 1      # a project file always holds exactly one project

CTX = "MainWindow"
PRODUCT = "PDX Translator"      # the product name is not translated


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(PRODUCT)
        self.project_name: str | None = None
        settings.ensure_dirs()
        rules_state.load_global()
        self.conn = None
        self.project_path: Path | None = None

        self.stack = QStackedWidget()
        self.start_screen = StartScreen()
        self.editor_screen = EditorScreen()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.editor_screen)
        self.setCentralWidget(self.stack)

        self.start_screen.projectOpened.connect(lambda p: self.open_project(Path(p)))
        self.start_screen.deleteRequested.connect(self._delete_project)
        self.editor_screen.statsChanged.connect(self._update_status_bar)
        self.editor_screen.manageTmRequested.connect(self._tm_manager)
        self.editor_screen.selectionChanged.connect(self._on_selection_changed)

        # Permanent widgets: temporary messages (showMessage) do not cover them,
        # otherwise the counter would vanish after every notification
        self.selection_label = QLabel()
        self.statusBar().addPermanentWidget(self.selection_label)
        self.stats_label = QLabel()
        self.statusBar().addPermanentWidget(self.stats_label)
        self.chips = StatusChipsBar()
        self.chips.chipClicked.connect(self._on_chip_filter)
        self.chips.issuesClicked.connect(self._toggle_only_issues)
        self.statusBar().addPermanentWidget(self.chips)
        self.chips.hide()

        self.context_bar = ContextBar()
        self.context_bar.tmSourcesChanged.connect(self.editor_screen.refresh_current)
        self._build_menu()
        self.toolbar = build_toolbar(self, self.actions)
        self.addToolBar(self.toolbar)
        self._restore_view_settings()
        self._restore_geometry()
        self.statusBar().showMessage(
            translate("MainWindow", "Choose or create a project"))

        # The wizard comes before the project is opened: it sets the interface
        # language, and meeting it in the middle of an already open window would
        # mean redrawing everything twice.
        self._run_first_start()
        if prefs.get("general/reopen_last"):
            last = settings.last_project_path()
            if last and last.is_file():
                self.open_project(last)

    # --- first start ---

    def _run_first_start(self) -> None:
        from pdxloc.gui.welcome_dialog import WelcomeDialog, needed

        if not needed():
            return
        dlg = WelcomeDialog(self)
        dlg.buildDatabaseRequested.connect(self._build_tm_database)
        dlg.createProjectRequested.connect(self.start_screen.create_project)
        dlg.openProjectRequested.connect(self._open_file)
        dlg.exec()

    def _build_tm_database(self) -> None:
        """Open the translation memory straight on the database-building tab."""
        from pdxloc.gui.tm_window import TmWindow

        dlg = TmWindow(self.conn, self)
        dlg.show_build_tab()
        dlg.exec()
        self.context_bar.refresh()

    def _offer_tm_databases(self) -> None:
        """Remind about the memory databases if there is not a single one.

        Without a database the tool loses half its point: the strings the mod
        copied from the game have to be translated by hand. The reminder goes
        through `ask_once` — it can be silenced forever, otherwise it would turn
        into nagging and people would start closing it unread.
        """
        from pdxloc.gui import ask

        if project.any_tm_database():
            return
        answer = ask.ask_once(
            self, ask.NO_TM_DATABASES,
            translate("MainWindow", "Translation memory"),
            translate("MainWindow",
                      "There is not a single translation memory database.\n\n"
                      "A database built from your copy of the game fills in "
                      "strings the mod copied from it — often hundreds of "
                      "them.\n\nBuild one now?"))
        if answer == QMessageBox.Yes:
            self._build_tm_database()

    # --- the menu ---

    def _build_menu(self) -> None:
        """Build the menu from the spec in `gui/actions.py`.

        The layout and the order live there, here — only the slots: otherwise
        the composition of the menu would crawl apart over the code again, and
        the toolbar would start keeping copies of its own actions.
        """
        self.actions = ActionRegistry()
        self.actions.build(self, self.editor_screen.table)
        # project actions live here, row actions live in the editor screen
        connect = self.actions.connect
        connect("projects", self.show_start)
        connect("open", self._open_file)
        connect("save_as", self._save_as)
        connect("import", self._import_translations)
        connect("export", self._export)
        connect("prefs", self._show_prefs)
        connect("quit", self.close)
        connect("undo", self._undo_last)
        connect("scan", self.scan_current)
        connect("qa", self._show_qa)
        connect("qa_rules", self._show_qa_rules)
        connect("qa_ignores", self._show_qa_ignores)
        connect("actualize_cosmetic", self._actualize_cosmetic)
        connect("archive", self._show_archive)
        connect("en_root", self._change_en_root)
        connect("ru_root", self._change_translation_root)
        connect("project_languages", self._change_languages)
        connect("tm", self._tm_manager)
        connect("glossary", self._glossary)
        connect("mt_batch", self._machine_translate_batch)
        connect("open_bdd", self._open_bdd_dir)
        connect("shortcuts", self._show_shortcuts)
        connect("about", self._about)
        connect("show_toolbar", self._toggle_toolbar)
        connect("show_tree", self._toggle_tree)
        connect("show_context", self._toggle_context)
        self.editor_screen.bind_actions(self.actions)

        self._populate_menus()

        # Old names: the tests and outside code reach for win.act_export and its
        # neighbours. Now those are the same objects as in the toolbar and the
        # context menu.
        for action_id, action in self.actions:
            setattr(self, f"act_{action_id}", action)

        self.editor_screen.filtersChanged.connect(self._sync_filter_views)
        # The subscriptions live here and not in the submenu builders: those are
        # called anew at every change of language, and the connections would
        # pile up with every switch.
        theme.on_change(self._sync_theme_menu)
        rules_state.on_change(self._sync_qa_preset_menu)
        language.on_change(self._retranslate)
        self._set_project_actions(False)

    def _populate_menus(self) -> None:
        """Build the menu bar from the spec — once in the life of the window.

        Rebuilding it at a change of language will not do: `QMenuBar.clear()`
        takes the items off, but the QMenu objects themselves stay children of
        the menu bar, and the radio group items with them. Over three language
        switches they piled up fourfold (checked by `test_language_switch.py`).
        That is why the menu is renamed in place, see `_retranslate_menus`.
        """
        self._menus: dict[str, object] = {}
        self._submenus: dict[str, object] = {}
        for title, ids in MENU:
            menu = self.menuBar().addMenu(translate("MainWindow", title))
            self._menus[title] = menu
            for action_id in ids:
                if action_id is SEP:
                    menu.addSeparator()
                elif action_id == "@status":
                    self._submenus["status"] = self._build_status_menu(menu)
                elif action_id == "@sort":
                    self._submenus["sort"] = self._build_sort_menu(menu)
                elif action_id == "@theme":
                    self._submenus["theme"] = self._build_theme_menu(menu)
                elif action_id == "@qa_preset":
                    self._submenus["qa_preset"] = self._build_qa_preset_menu(menu)
                elif action_id == "@columns":
                    self._submenus["columns"] = self._build_columns_menu(menu)
                elif action_id == "@buttons":
                    self._submenus["buttons"] = self._build_buttons_menu(menu)
                else:
                    menu.addAction(self.actions[action_id])

    # The labels of the radio groups come from one source for both the build and
    # the translation: were they to diverge, part of the items would stay in the
    # old language after a switch.
    def _status_items(self):
        return ([(None, translate("MainWindow", "All"))]
                + [(s.value, statuses_mod.label(s)) for s in STATUS_ORDER])

    def _sort_items(self):
        return [(None, translate("MainWindow", "No sorting"))] + [
            (col, translate("UnitsTable", label)) for col, label in SORT_COLUMNS]

    def _theme_items(self):
        return [(name, translate("Theme", label))
                for name, label in theme.THEME_LABELS.items()]

    def _qa_preset_items(self):
        """The presets in shop-window order: the one that suits the project first, and marked.

        The mark is computed instead of standing in the label: «(recommended)»
        used to be written into `ck3_ru` and promised to everyone in a row,
        including the HOI4 translator, for whom a neighbouring set is the
        recommended one.
        """
        game, locale = rules_state.game(), rules_state.locale()
        best = qa_rules.recommended(game, locale)
        items = []
        for name in qa_rules.display_order(game, locale):
            label = qa_rules.preset_label(name)
            if name == best:
                label = fill(translate("QaRules", qa_rules.RECOMMENDED_MARK), label)
            items.append((name, label))
        return items

    def _column_items(self):
        return [(col, translate("UnitsTable", label)) for col, label in DATA_COLUMNS]

    def _button_items(self):
        return [(action_id, translate("Actions", act_spec.BY_ID[action_id].text))
                for action_id in act_spec.STATUS_BUTTONS]

    def _retranslate_menus(self) -> None:
        """Rename the menus and the radio group items without recreating anything."""
        for title, menu in self._menus.items():
            menu.setTitle(translate("MainWindow", title))
        titles = {"status": "Show", "sort": "Sort",
                  "theme": "Theme", "qa_preset": "Rule preset",
                  "columns": "Columns", "buttons": "Status buttons"}
        for key, menu in self._submenus.items():
            menu.setTitle(translate("MainWindow", titles[key]))
        groups = (
            (self._status_items(), self.status_actions),
            (self._sort_items(), self.sort_actions),
            (self._theme_items(), self.theme_actions),
            (self._qa_preset_items(), self.qa_preset_actions),
            (self._column_items(), self.column_actions),
            (self._button_items(), self.button_actions),
        )
        for items, made in groups:
            for value, label in items:
                action = made.get(value)
                if action is not None:
                    action.setText(label)
        for name, action in self.qa_preset_actions.items():
            action.setToolTip(
                translate("QaRules", qa_rules.PRESET_NOTES.get(name, "")))
        self.sort_desc_action.setText(translate("MainWindow", "Descending"))

    def _retranslate(self) -> None:
        """Redraw everything that lives longer than one opening.

        The dialogs are absent from the list deliberately: each is created anew
        on opening and takes the language itself. What needs rereading is
        exactly the long-livers — the menu, the commands, the toolbar, the
        screens and the header of the table.
        """
        self.actions.retranslate()
        self._retranslate_menus()
        self._sync_filter_views()
        self._sync_theme_menu()
        self._sync_qa_preset_menu()
        self.toolbar.setWindowTitle(translate("Toolbar", "Toolbar"))
        self.context_bar.retranslate()
        self.chips.retranslate()
        self.start_screen.retranslate()
        self.editor_screen.retranslate()
        self._update_window_title()
        if self.conn is not None:
            self._update_status_bar()

    def _build_status_menu(self, parent):
        menu = parent.addMenu(translate("MainWindow", "Show"))
        self.status_actions = self.actions.radio_group(
            menu, menu, self._status_items(), self.editor_screen.set_status_filter)
        self.status_actions[None].setChecked(True)
        return menu

    def _build_sort_menu(self, parent) -> None:
        """A mirror of the sorting by the column headers.

        Needed for the same reason the chips duplicate the combo box: a state
        reachable only by a mouse click on a 26-pixel header cannot be got at
        from the keyboard and cannot be seen in a test.
        """
        menu = parent.addMenu(translate("MainWindow", "Sort"))
        self.sort_actions = self.actions.radio_group(
            menu, menu, self._sort_items(), self._on_sort_column)
        self.sort_actions[None].setChecked(True)
        menu.addSeparator()
        self.sort_desc_action = QAction(
            translate("MainWindow", "Descending"), menu, checkable=True)
        self.sort_desc_action.triggered.connect(self._on_sort_desc)
        menu.addAction(self.sort_desc_action)
        return menu

    def _build_columns_menu(self, parent):
        """Which columns of the table to show (in EET this is an item of "View" too).

        The key of the setting is the English label of the column and not its
        number: were somebody to insert a column in the middle, the numbers
        would shift and hide a foreign one. A renamed label will simply stop
        matching and the column will come back visible — of the two failures
        that one is the more harmless.
        """
        menu = parent.addMenu(translate("MainWindow", "Columns"))
        self.column_actions = self.actions.check_group(
            menu, menu, self._column_items(), self._toggle_column)
        return menu

    def _build_buttons_menu(self, parent):
        menu = parent.addMenu(translate("MainWindow", "Status buttons"))
        menu.setToolTipsVisible(True)
        self.button_actions = self.actions.check_group(
            menu, menu, self._button_items(), self._toggle_status_button)
        for action in self.button_actions.values():
            action.setToolTip(translate(
                "MainWindow", "Hides the toolbar button only — the command "
                              "stays in the menu and its shortcut keeps working"))
        return menu

    def _hidden_columns(self) -> set[str]:
        raw = settings.qsettings().value("view/hidden_columns", "")
        return {p for p in str(raw or "").split("|") if p}

    def _toggle_column(self, column: int, visible: bool) -> None:
        label = dict(DATA_COLUMNS)[column]
        hidden = self._hidden_columns()
        hidden.discard(label) if visible else hidden.add(label)
        if len(hidden) >= len(DATA_COLUMNS):
            # hiding the table whole is not a setting but a breakage
            hidden.discard(label)
            self.column_actions[column].setChecked(True)
            return
        settings.qsettings().setValue("view/hidden_columns", "|".join(sorted(hidden)))
        self.editor_screen.table.setColumnHidden(column, not visible)

    def _toggle_status_button(self, action_id: str, visible: bool) -> None:
        settings.qsettings().setValue(f"view/button_{action_id}", visible)
        widget = self.toolbar.widgetForAction(self.actions[action_id])
        if widget is not None:
            # we hide the button and not the action: the same QAction lives in
            # the "Translation" menu and in the context menu of the table, and
            # there it is needed
            widget.setVisible(visible)

    def _on_sort_column(self, column) -> None:
        self.editor_screen.state.set_sort(
            column, self.sort_desc_action.isChecked())

    def _on_sort_desc(self, descending: bool) -> None:
        state = self.editor_screen.state
        if state.sort.column is not None:
            state.set_sort(state.sort.column, descending)

    def _sync_sort_menu(self) -> None:
        spec = self.editor_screen.state.sort_spec
        column, descending = spec if spec else (None, False)
        action = self.sort_actions.get(column)
        if action is not None:
            action.setChecked(True)
        self.sort_desc_action.setChecked(descending)
        self.sort_desc_action.setEnabled(column is not None)

    def _build_theme_menu(self, parent):
        menu = parent.addMenu(translate("MainWindow", "Theme"))
        self.theme_actions = self.actions.radio_group(
            menu, menu, self._theme_items(), self._set_theme)
        self.theme_actions[theme.current()].setChecked(True)
        return menu

    def _sync_theme_menu(self) -> None:
        self.theme_actions[theme.current()].setChecked(True)

    def _build_qa_preset_menu(self, parent) -> None:
        """The ready-made rule sets — a radio group, like the theme and the sorting.

        Changing the set from the menu writes into the global layer: this is a
        choice of strictness in general and not a setting for a particular mod.
        The fine tuning of individual rules lives in the Shift+F6 window and can
        write into the project layer.
        """
        menu = parent.addMenu(translate("MainWindow", "Rule preset"))
        self._qa_preset_menu = menu
        # The separator parts the recommended set from the rest. Its parent is
        # the window and not the menu: it leaves the menu and comes back at
        # every change of project, and it must not die together with it.
        self._qa_preset_separator = QAction(self)
        self._qa_preset_separator.setSeparator(True)
        self.qa_preset_actions = self.actions.radio_group(
            menu, menu, self._qa_preset_items(), self._set_qa_preset)
        for name, action in self.qa_preset_actions.items():
            action.setToolTip(translate("QaRules", qa_rules.PRESET_NOTES.get(name, "")))
        self._sync_qa_preset_menu()
        return menu

    def _set_qa_preset(self, name: str) -> None:
        overlay = dict(rules_state.global_overlay())
        overlay["version"] = qa_rules.OVERLAY_VERSION
        overlay["preset"] = None if name == qa_rules.CUSTOM else name
        rules_state.save_global(overlay)
        self.editor_screen.refresh_issues()
        self.statusBar().showMessage(
            translate("MainWindow", "Check preset: %1").replace(
                "%1", qa_rules.preset_label(name)), 5000)

    def _sync_qa_preset_menu(self) -> None:
        """Mark the set in force and lift the recommended one to the top.

        The items are moved about with `removeAction`/`addAction` and not by
        rebuilding the menu. `QMenu.clear()` will not do here: it **deletes**
        the actions whose parent the menu itself is — and recreating them would
        mean piling up items in the radio group, exactly as `_populate_menus`
        warns about.

        Called on the signal from `rules_state`, and that one comes both on
        opening and on closing a project — so the mark appears and disappears
        by itself.
        """
        menu = self._qa_preset_menu
        for action in list(menu.actions()):
            menu.removeAction(action)
        best = qa_rules.recommended(rules_state.game(), rules_state.locale())
        for name, label in self._qa_preset_items():
            action = self.qa_preset_actions.get(name)
            if action is None:
                continue
            action.setText(label)
            menu.addAction(action)
            if name == best:
                menu.addAction(self._qa_preset_separator)

        action = self.qa_preset_actions.get(rules_state.preset())
        if action is not None:
            action.setChecked(True)

    def _sync_filter_views(self) -> None:
        """Show the current filter in all of its shop windows at once.

        The status filter is set from five places — the combo box, the status
        bar chips, the file tree, the scan summary and the menu. Every place
        used to know only about itself: a chip lit up only when the chip itself
        was clicked.
        """
        status = self.editor_screen.state.status
        self.chips.set_active_filter(status)
        action = self.status_actions.get(status)
        if action is not None:
            action.setChecked(True)
        self._sync_issues_chip()
        self._sync_sort_menu()

    def _sync_issues_chip(self) -> None:
        self.chips.set_issues(self.editor_screen.model.issue_count(),
                              self.editor_screen.state.only_issues)

    def _set_project_actions(self, enabled: bool) -> None:
        self.actions.set_enabled(enabled)

    # --- the view ---

    def _restore_view_settings(self) -> None:
        s = settings.qsettings()
        self.act_show_toolbar.setChecked(s.value("view/toolbar", True, type=bool))
        self.act_show_tree.setChecked(s.value("view/file_tree", True, type=bool))
        self.act_show_context.setChecked(s.value("view/context", True, type=bool))

        hidden = self._hidden_columns()
        for column, label in DATA_COLUMNS:
            # setChecked will pull toggled itself and hide the column — there is
            # no need to hide it here a second time
            self.column_actions[column].setChecked(label not in hidden)
        for action_id in act_spec.STATUS_BUTTONS:
            self.button_actions[action_id].setChecked(
                s.value(f"view/button_{action_id}", True, type=bool))

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
        """The list of keys is gathered from the action spec — it cannot lie.

        The layout is the same as in ESP/ESM Translator. The list used to be
        written by hand and fell behind the code at every edit of the menu.
        """
        rows = [
            (" / ".join(QKeySequence(k).toString() for k in spec.keys), spec.text)
            for spec in ACTIONS if spec.keys
        ]
        rows = [(keys, translate("Actions", text)) for keys, text in rows]
        rows.append((translate("MainWindow", "F2, double click"),
                     translate("MainWindow", "Edit the translation in the cell")))
        body = "".join(f"<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{v}</td></tr>"
                       for k, v in rows)
        QMessageBox.information(
            self, translate("MainWindow", "Keyboard shortcuts"),
            f"<table>{body}</table>")

    # --- projects ---

    def show_start(self) -> None:
        """Return to the list of projects, letting the open project go.

        The connection has to be closed: `open_project` works in WAL mode, `-wal`
        and `-shm` live next to the file, and while they are held the project
        file can be neither deleted nor moved. The screen used to just switch
        over, and a project opened at start-up stayed busy the whole time the
        user was looking through the list.
        """
        self._close_project()
        self.project_path = None
        self._update_window_title()
        self.start_screen.reload()
        self.stack.setCurrentWidget(self.start_screen)
        self.statusBar().showMessage(
            translate("MainWindow", "Choose or create a project"))

    def _delete_project(self, raw: str) -> None:
        """Delete a project file at the request of the start screen."""
        path = Path(raw)
        known = next((d for d in settings.recent_projects()
                      if Path(d["path"]) == path), {})
        name = known.get("name") or path.stem
        done, total = known.get("done", 0), known.get("total", 0)
        progress = fill(translate(
            "MainWindow", "\n\nTranslations that will be lost: %1 of %2 rows."),
            done, total) if total else ""
        where = (translate("MainWindow", "The file goes to the recycle bin")
                 if trash.available()
                 else translate("MainWindow", "The file will be deleted"))

        box = QMessageBox(
            QMessageBox.Warning, translate("MainWindow", "Delete project"),
            fill(translate("MainWindow",
                           "Delete the project «%1» together with its file?\n\n"
                           "%2%3\n\n%4. Mod files and translation memory "
                           "databases are untouched."),
                 name, path, progress, where),
            parent=self)
        delete_btn = box.addButton(translate("MainWindow", "Delete"),
                                   QMessageBox.DestructiveRole)
        keep_btn = box.addButton(translate("MainWindow", "Cancel"),
                                 QMessageBox.RejectRole)
        box.setDefaultButton(keep_btn)      # a dangerous action must not sit on Enter
        also_backups = QCheckBox(
            translate("MainWindow", "Delete the backups next to it as well"))
        box.setCheckBox(also_backups)
        box.exec()
        if box.clickedButton() is not delete_btn:
            return

        if self.project_path is not None and self.project_path == path:
            self.show_start()               # closes the connection and drops the WAL
        try:
            removed = project.delete_project_file(
                path, with_backups=also_backups.isChecked())
        except OSError as e:
            QMessageBox.critical(
                self, translate("MainWindow", "Delete project"),
                fill(translate("MainWindow",
                               "Could not delete the file:\n%1\n\n%2\n\n"
                               "Most likely it is open in another program."), path, e))
            return
        settings.forget_project(path)
        if settings.last_project_path() == path:
            settings.set_last_project_path(None)
        self.start_screen.reload()
        self.statusBar().showMessage(
            fill(translate("MainWindow", "Project deleted: %1 (%2 files)"),
                 path.name, len(removed)), 6000)
        if removed.bypassed_trash:
            # We promised the recycle bin — and Windows does not take a file
            # there if it does not fit its quota. A translation project weighs
            # hundreds of megabytes, so the case is a live one. Keeping silent
            # will not do: the human will go looking for the file and not find it.
            QMessageBox.warning(
                self, translate("MainWindow", "Delete project"),
                fill(translate("MainWindow",
                               "The recycle bin did not accept the file, so it "
                               "was deleted permanently:\n%1\n\nUsually this "
                               "means the file is larger than the bin allows."),
                     "\n".join(str(p) for p in removed.bypassed_trash)))

    def _offer_right_pen(self, path: Path) -> Path:
        """A project of a foreign pen — offer to move it. Returns the path to the file.

        We ask **before opening**: an open project holds a `-wal`, and moving it
        then would be too late — we would have to close what was just opened.

        It fires only inside the projects folder. A project file is portable, and
        people put it next to the mod or hand it to another person on purpose —
        pestering about that would mean becoming the very trouble we defend
        against.
        """
        game_id = project.read_game(path)
        if game_id is None:
            return path
        try:
            pen_root = settings.projects_dir().resolve()
            here = path.resolve().parent
            target = settings.projects_pen(game_id)
            if here == target.resolve():
                return path             # already in its own pen
            if here == pen_root:
                where = None            # in the root of the pens — also out of place
            elif here.parent == pen_root and games.by_folder(here.name):
                where = games.by_folder(here.name)
            else:
                # either the project lives a life of its own outside the projects
                # folder, or it lies in a folder the human set up. Either way —
                # not our business
                return path
        except OSError:
            return path
        if QMessageBox.question(
                self, translate("MainWindow", "Project of another game"),
                fill(translate(
                    "MainWindow",
                    "The project «%1» belongs to %2, but lies in the folder of "
                    "%3.\n\nMove it to %4?"),
                    path.stem, games.title(game_id),
                    games.title(where) if where else translate(
                        "MainWindow", "no game in particular"),
                    target)) != QMessageBox.Yes:
            return path
        try:
            moved = project.move_project_file(path, target)
        except OSError as e:
            QMessageBox.warning(
                self, translate("MainWindow", "Project of another game"),
                fill(translate("MainWindow", "Could not move the file:\n%1"), e))
            return path
        settings.forget_project(path)
        return moved

    def open_project(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            QMessageBox.warning(
                self, translate("MainWindow", "Project"),
                fill(translate("MainWindow", "Project file not found:\n%1"), path))
            return
        path = self._offer_right_pen(path)
        try:
            conn = project.open_project(path)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(
                self, translate("MainWindow", "Project"),
                fill(translate("MainWindow", "Could not open the project:\n%1"), e))
            return

        self._close_project()
        self.conn = conn
        self.project_path = path
        self.project_name = project.project_name(conn)
        self._update_window_title()
        conn.execute("UPDATE projects SET last_opened_at = datetime('now') WHERE id = 1")
        conn.commit()
        settings.set_last_project_path(path)

        # the rule set comes before the first recount of the issues: otherwise
        # the table would count the «!» column with the built-in values instead
        # of the setting of the project
        rules_state.open_project(conn)

        has_units = conn.execute("SELECT 1 FROM units LIMIT 1").fetchone()
        self.editor_screen.set_session(conn)
        if not has_units:
            self.scan_current()
        # strings with nothing to translate (markup only) must not hang among
        # the untranslated ones — in projects of former versions too. Exactly
        # once per project: otherwise a cleanup undone with Ctrl+Z would come
        # back at the next opening.
        auto_ignored = 0
        if not project.get_auto_ignore_done(conn):
            auto_ignored = unit_ops.auto_ignore_untranslated(conn, PROJECT_ID)
            project.set_auto_ignore_done(conn)
        self.editor_screen.open_project(PROJECT_ID)
        self.stack.setCurrentWidget(self.editor_screen)
        self._set_project_actions(True)
        self.context_bar.set_project(conn)
        self.editor_screen.file_tree.setVisible(self.act_show_tree.isChecked())
        self._update_status_bar()
        self.statusBar().clearMessage()      # remove the invitation to choose a project
        self._offer_tm_databases()
        if auto_ignored:
            self.statusBar().showMessage(
                fill(translate("MainWindow",
                               "%1 rows with no translatable text were marked as "
                               "ignored (bare tags such as [GetName], empty "
                               "values) — Ctrl+Z undoes it"),
                     auto_ignored), 8000)

    def _update_window_title(self) -> None:
        self.setWindowTitle(
            f"{self.project_name} — {PRODUCT}" if self.project_name else PRODUCT)

    def _close_project(self) -> None:
        if self.conn is not None:
            self.editor_screen.close_session()
            stats = project_stats(self.conn, PROJECT_ID)
            settings.remember_project(
                self.project_path, project.project_name(self.conn),
                stats.done, stats.total, game=project.game(self.conn))
            # the journal goes into the database: otherwise a `-wal` the size of
            # the project is left next to it, and the next opening starts by
            # reading those megabytes
            project.checkpoint(self.conn)
            self.conn.close()
            self.conn = None
        self.project_name = None
        self._update_window_title()
        rules_state.close_project()
        # project actions without a project only confuse: they used to stay
        # enabled and fall over on an empty connection
        self._set_project_actions(False)
        self.context_bar.set_project(None)
        self.chips.hide()
        self.stats_label.clear()
        self.selection_label.clear()

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, translate("MainWindow", "Open project"),
            str(settings.projects_dir()),
            fill(translate("MainWindow",
                           "Translation project (*%1);;All files (*)"),
                 settings.PROJECT_EXT))
        if path:
            self.open_project(Path(path))

    def _save_as(self) -> None:
        if self.conn is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, translate("MainWindow", "Save project as"),
            str(settings.projects_dir()),
            fill(translate("MainWindow", "Translation project (*%1)"),
                 settings.PROJECT_EXT))
        if not path:
            return
        target = Path(path)
        if target == self.project_path:
            return
        target.unlink(missing_ok=True)
        try:
            project.save_project_as(self.conn, target)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(
                self, translate("MainWindow", "Saving"),
                fill(translate("MainWindow", "Could not save:\n%1"), e))
            return
        QMessageBox.information(
            self, translate("MainWindow", "Saving"),
            fill(translate("MainWindow",
                           "Project saved:\n%1\n\nOpening the copy."), target))
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
                translate("MainWindow",
                          "Scan interrupted — changes were not saved"), 6000)
        elif dlg.error:
            QMessageBox.critical(
                self, translate("MainWindow", "Scanning"),
                fill(translate("MainWindow", "Error:\n%1"), dlg.error))
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    # --- service ---

    def _update_status_bar(self) -> None:
        if self.conn is None:
            return
        stats = project_stats(self.conn, PROJECT_ID)
        self.stats_label.setText(format_status_bar(stats))
        self.chips.set_stats(stats)
        self._sync_issues_chip()
        self.chips.show()

    def _on_selection_changed(self, count: int) -> None:
        """The reach of a bulk operation is visible before the press, not after."""
        self.selection_label.setText(
            fill(translate("MainWindow", "Rows selected: %1"), count)
            if count > 1 else "")

    def _on_chip_filter(self, status_value: str) -> None:
        self.editor_screen.set_status_filter(status_value or None)

    def _toggle_only_issues(self) -> None:
        """The «!» chip is the same shop window as the toolbar tick and the menu item.

        Through the `QAction` and not past it: the action already has a slot
        that calls `set_only_issues` and updates the other shop windows —
        otherwise the chip would light up while the tick on the toolbar stayed
        clear.
        """
        self.act_only_issues.toggle()

    def _show_qa(self) -> None:
        """A full check of the project as a separate report.

        The everyday issues are visible in the «!» column of the table, so the
        panel no longer takes up room on the screen permanently.
        """
        from pdxloc.gui.qa_panel import QaReportDialog

        if self.conn is None:
            return
        dlg = QaReportDialog(self.conn, PROJECT_ID, self)
        dlg.jumpToUnit.connect(self.editor_screen.jump_to_unit)
        dlg.configureRule.connect(self._show_qa_rules)
        dlg.exec()
        self.editor_screen.refresh_issues()

    def _show_qa_rules(self, rule_id: str = "", initial_tab: int = 0) -> None:
        """The window for setting up the checks. Works without an open project too.

        Without a project the hits cannot be counted, but the rule set is
        global, and forbidding its setup until a mod is open would be odd.
        """
        from pdxloc.gui.rules_window import RulesWindow

        dlg = RulesWindow(self.conn, self.project_path, self,
                          initial_tab=initial_tab,
                          current_pair=self.editor_screen.current_pair)
        dlg.rulesChanged.connect(self.editor_screen.refresh_issues)
        if rule_id:
            dlg.select_rule(rule_id)
        dlg.exec()

    def _show_qa_ignores(self) -> None:
        self._show_qa_rules(initial_tab=1)

    def _actualize_cosmetic(self) -> None:
        """Confirm the translations of rows where the mod author edited the formatting only."""
        if self.conn is None:
            return
        ids = unit_ops.cosmetic_stale_ids(self.conn, PROJECT_ID)
        if not ids:
            QMessageBox.information(
                self, translate("MainWindow", "Cosmetic edits"),
                translate("MainWindow",
                          "There are no outdated rows with cosmetic edits.\n\n"
                          "Those are changes of punctuation, case and spaces — "
                          "when the meaning of the original did not change."))
            return
        answer = QMessageBox.question(
            self, translate("MainWindow", "Cosmetic edits"),
            fill(translate("MainWindow",
                           "Confirm translations of %1 rows where the original was "
                           "edited cosmetically only?\n\nThe translations themselves "
                           "do not change — the «Outdated» mark is removed. The "
                           "operation can be undone (Ctrl+Z)."), len(ids)))
        if answer != QMessageBox.Yes:
            return
        batch = unit_ops.new_batch_id()
        changed = unit_ops.actualize(self.conn, ids, batch_id=batch)
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()
        self.statusBar().showMessage(
            fill(translate("MainWindow", "Rows actualized: %1"), changed), 6000)

    def _change_en_root(self) -> None:
        """Change the source folder and reread it at once.

        Without a scan the change means nothing: the rows in the database stay
        from the former folder. That is why we offer the scan right here instead
        of leaving the project in the state "the path is new, the contents are
        old".
        """
        from pdxloc.gui.root_dialog import EnRootDialog

        if self.conn is None:
            return
        dlg = EnRootDialog(self.conn, PROJECT_ID, self)
        if not dlg.exec():
            return
        answer = QMessageBox.question(
            self, translate("MainWindow", "Change of the original folder"),
            translate("MainWindow",
                      "The folder has changed. Scan the project now?\n\n"
                      "Scanning re-reads the files: translations are kept, changed "
                      "rows become «Outdated»."))
        if answer == QMessageBox.Yes:
            self.scan_current()

    def _change_translation_root(self) -> None:
        """Change the folder the translation is read from and written into.

        A scan is offered for the same reason as with the original folder: until
        it runs, the project holds what the former folder gave. A project that
        had no folder at all has nothing to reread, so there we keep quiet.
        """
        from pdxloc.gui.root_dialog import TranslationRootDialog

        if self.conn is None:
            return
        had_root = project.translation_root(self.conn, PROJECT_ID) is not None
        dlg = TranslationRootDialog(self.conn, PROJECT_ID, self)
        if not dlg.exec():
            return
        if project.translation_root(self.conn, PROJECT_ID) is None or not had_root:
            return
        answer = QMessageBox.question(
            self, translate("MainWindow", "Change of the translation folder"),
            translate("MainWindow",
                      "The folder has changed. Scan the project now?\n\n"
                      "Scanning re-reads the files: the translation stays in the "
                      "project, and what the new folder holds is picked up."))
        if answer == QMessageBox.Yes:
            self.scan_current()

    def _change_languages(self) -> None:
        """Change the project languages and, if the language folder was touched, reread.

        A change of the folder language changes which files the scanner counts
        as its own — without a scan the project would be left in the state "the
        language is new, the contents are old". A change of the text language
        alone does not touch the files, and there is no need to call the scan.
        """
        from pdxloc.gui.languages_dialog import LanguagesDialog

        if self.conn is None:
            return
        dlg = LanguagesDialog(self.conn, PROJECT_ID, self)
        needs_scan: list[bool] = []
        dlg.languagesChanged.connect(needs_scan.append)
        if not dlg.exec():
            return
        # the rule set depends on the target language: the Russian rules go quiet
        rules_state.open_project(self.conn)
        self.context_bar.refresh()
        self.editor_screen.refresh_issues()
        if needs_scan and needs_scan[0]:
            answer = QMessageBox.question(
                self, translate("MainWindow", "Project languages"),
                translate("MainWindow",
                          "The language of the folders changed. Scan the "
                          "project now?\n\nScanning re-reads the files under "
                          "the new names."))
            if answer == QMessageBox.Yes:
                self.scan_current()

    def _undo_last(self) -> None:
        if self.conn is None:
            return
        info = unit_ops.last_batch(self.conn)
        if info is None:
            QMessageBox.information(self, translate("MainWindow", "Undo"),
                                    translate("MainWindow", "Nothing to undo."))
            return
        batch_id, origin, count = info
        labels = {
            "actualize": QT_TRANSLATE_NOOP("MainWindow", "actualization"),
            "bulk": QT_TRANSLATE_NOOP("MainWindow", "status change"),
            "manual": QT_TRANSLATE_NOOP("MainWindow", "translation edit"),
            "replace": QT_TRANSLATE_NOOP("MainWindow", "bulk replace"),
            "glossary": QT_TRANSLATE_NOOP("MainWindow", "glossary rules"),
            "tm": QT_TRANSLATE_NOOP("MainWindow", "fill from memory"),
            "import": QT_TRANSLATE_NOOP("MainWindow", "translation import"),
            "auto_ignore": QT_TRANSLATE_NOOP(
                "MainWindow", "auto-ignore of rows with nothing to translate"),
            "machine": QT_TRANSLATE_NOOP("MainWindow", "machine translation"),
        }
        what = translate("MainWindow", labels[origin]) if origin in labels else origin
        answer = QMessageBox.question(
            self, translate("MainWindow", "Undo operation"),
            fill(translate("MainWindow",
                           "Undo the last operation (%1) and return %2 rows to "
                           "their previous state?"), what, count))
        if answer != QMessageBox.Yes:
            return
        restored = unit_ops.undo_batch(self.conn, batch_id)
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()
        self.statusBar().showMessage(
            fill(translate("MainWindow", "Rows reverted: %1"), restored), 6000)

    def _tm_manager(self) -> None:
        """One window for the whole translation memory: records, databases and building."""
        from pdxloc.gui.tm_window import TmWindow

        if self.conn is None:
            return
        window = TmWindow(self.conn, self)
        window.sources.sourcesChanged.connect(self._on_tm_sources_changed)
        window.build.databasesChanged.connect(self.context_bar.refresh)
        window.exec()
        self.editor_screen.refresh_current()

    def _glossary(self) -> None:
        """The glossary window: the accepted terms and the queue of candidates.

        The statistics run goes over the project file on its own connection, so
        the window needs the path and not only the connection.
        """
        from pdxloc.gui.glossary_window import GlossaryWindow

        if self.conn is None or self.project_path is None:
            return
        window = GlossaryWindow(self.conn, self.project_path, self)
        # an accepted term is obliged to light up in the source field at once,
        # without waiting for the window to close: the translator accepts a term
        # exactly because they see it in the row in front of them
        window.glossaryChanged.connect(self.editor_screen.detail.reload_glossary)
        window.exec()
        self.editor_screen.detail.reload_glossary()

    def _machine_translate_batch(self) -> None:
        """Bulk machine translation: the reach, the estimate, the run, the summary."""
        from pdxloc.gui.mt_dialog import MtDialog

        if self.conn is None or self.project_path is None:
            return
        selected = [i for i in self.editor_screen.table.selected_unit_ids()
                    if i is not None]
        dialog = MtDialog(self.conn, PROJECT_ID, self.project_path,
                          selected_ids=selected, parent=self)
        dialog.translated.connect(self._after_machine_translation)
        dialog.showUnitRequested.connect(self.editor_screen.jump_to_unit)
        dialog.exec()

    def _after_machine_translation(self) -> None:
        """The rows were written by the worker on its own connection — we reread it all."""
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    def _on_tm_sources_changed(self) -> None:
        """The set of databases changes at once — the hints and the header must see it."""
        self.editor_screen.refresh_current()
        self.context_bar.refresh()

    def _show_prefs(self) -> None:
        from pdxloc.gui.prefs_dialog import PreferencesDialog

        PreferencesDialog(self).exec()

    def _open_bdd_dir(self) -> None:
        shell.open_dir(settings.bdd_dir())

    def _show_archive(self) -> None:
        from pdxloc.gui.archive_dialog import ArchiveDialog

        ArchiveDialog(self.conn, self).exec()

    def _export(self) -> None:
        from pdxloc.gui.export_dialog import ExportDialog

        if self.conn is not None:
            ExportDialog(self.conn, PROJECT_ID, self).exec()

    def _import_translations(self) -> None:
        from pdxloc.gui.import_dialog import ImportDialog

        if self.conn is None:
            return
        dlg = ImportDialog(self.conn, PROJECT_ID, self)
        dlg.imported.connect(self._after_import)
        dlg.exec()

    def _after_import(self) -> None:
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    def _about(self) -> None:
        """The "About" window. It is also the notice of the terms of distribution.

        The GPL-3.0 itself asks for that ("How to Apply These Terms"): for a
        program with windows the notice of the absence of warranty is shown in
        the about box and not in a console, which we do not have.

        Qt is spoken of here as well, and that is not politeness: in the portable
        build Qt travels inside the archive (93 MB out of 120), that is, we
        distribute it, and the LGPL demands telling the recipient that the
        library is in there and under which licence.
        """
        from pdxloc import COPYRIGHT, __version__

        where = self.project_path or translate("MainWindow", "(no project open)")
        QMessageBox.about(
            self, PRODUCT,
            f"<b>{PRODUCT}</b> v{__version__}<br>{COPYRIGHT}<br><br>"
            + translate("MainWindow",
                        "A translator's workbench for the localisation of "
                        "Paradox game mods.<br>"
                        "Format: Paradox pseudo-YAML (UTF-8 with BOM) and the "
                        "older CSV.<br><br>")
            + translate("MainWindow",
                        "This program comes with ABSOLUTELY NO WARRANTY. It is "
                        "free software, and you are welcome to redistribute it "
                        "under the terms of the GNU General Public License, "
                        "version 3 or later — see the LICENSE file.<br><br>"
                        "Uses Qt through PySide6 under the GNU LGPL v3.<br><br>")
            + fill(translate("MainWindow", "Project: %1<br>Memory databases: %2"),
                   where, settings.bdd_dir()))

    # --- geometry ---

    def _restore_geometry(self) -> None:
        geo = settings.qsettings().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 800)

    def closeEvent(self, event) -> None:
        settings.qsettings().setValue("geometry", self.saveGeometry())
        # The column widths sit next to the geometry and for the same reason: a
        # human fitted the table to their screen, and making them do it at every
        # start is pointless (in EET this is `ColumnsSizes`).
        self.editor_screen.table.save_column_widths()
        self._close_project()
        super().closeEvent(event)

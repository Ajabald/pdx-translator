"""Главное окно: стек экранов, меню, статус-бар."""
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

PROJECT_ID = 1      # в файле проекта всегда ровно один проект

CTX = "MainWindow"
PRODUCT = "PDX Translator"      # имя продукта не переводится


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

        # Постоянные виджеты: временные сообщения (showMessage) их не перекрывают,
        # иначе счётчик пропадал бы после каждого уведомления
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

        # Мастер — до открытия проекта: он задаёт язык интерфейса, и увидеть
        # его посреди уже открытого окна значило бы перерисовать всё дважды.
        self._run_first_start()
        if prefs.get("general/reopen_last"):
            last = settings.last_project_path()
            if last and last.is_file():
                self.open_project(last)

    # --- первый запуск ---

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
        """Открыть память переводов сразу на вкладке сборки базы."""
        from pdxloc.gui.tm_window import TmWindow

        dlg = TmWindow(self.conn, self)
        dlg.show_build_tab()
        dlg.exec()
        self.context_bar.refresh()

    def _offer_tm_databases(self) -> None:
        """Напомнить про базы памяти, если их нет ни одной.

        Без базы инструмент теряет половину смысла: строки, скопированные модом
        из игры, приходится переводить руками. Напоминание проходит через
        `ask_once` — заглушить его можно навсегда, иначе оно превратилось бы в
        назойливость и его начали бы закрывать не читая.
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

    # --- меню ---

    def _build_menu(self) -> None:
        """Собрать меню по спеке `gui/actions.py`.

        Раскладка и порядок живут там, здесь — только слоты: иначе состав меню
        снова расползётся по коду, а панель инструментов начнёт заводить
        собственные копии действий.
        """
        self.actions = ActionRegistry()
        self.actions.build(self, self.editor_screen.table)
        # действия проекта — здесь, действия над строками — в экране редактора
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

        # Старые имена: тесты и внешний код обращаются к win.act_export и
        # соседям. Теперь это те же объекты, что в тулбаре и контекстном меню.
        for action_id, action in self.actions:
            setattr(self, f"act_{action_id}", action)

        self.editor_screen.filtersChanged.connect(self._sync_filter_views)
        # Подписки — здесь, а не в сборщиках подменю: те вызываются заново при
        # каждой смене языка, и связь копилась бы с каждым переключением.
        theme.on_change(self._sync_theme_menu)
        rules_state.on_change(self._sync_qa_preset_menu)
        language.on_change(self._retranslate)
        self._set_project_actions(False)

    def _populate_menus(self) -> None:
        """Собрать строку меню по спеке — один раз за жизнь окна.

        Пересобирать при смене языка нельзя: `QMenuBar.clear()` снимает пункты,
        но сами QMenu остаются детьми строки меню, а вместе с ними — пункты
        радиогрупп. За три переключения языка их накопилось вчетверо больше,
        чем было (проверяется `test_language_switch.py`). Поэтому меню
        переименовывается на месте, см. `_retranslate_menus`.
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

    # Подписи радиогрупп — одним источником на сборку и на перевод: разойдись
    # они, после смены языка часть пунктов осталась бы на старом.
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
        """Пресеты в порядке витрины: подходящий проекту — первым и с пометкой.

        Пометка вычисляется, а не стоит в ярлыке: раньше «(recommended)» было
        вписано в `ck3_ru` и обещалось всем подряд, в том числе переводчику
        HOI4, которому рекомендован соседний набор.
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
        """Переименовать меню и пункты радиогрупп, ничего не пересоздавая."""
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
        """Перерисовать всё, что живёт дольше одного открытия.

        Диалоги в списке отсутствуют намеренно: каждый создаётся заново при
        открытии и берёт язык сам. Перечитать нужно ровно долгожителей — меню,
        команды, панель, экраны и шапку таблицы.
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
        """Зеркало сортировки по заголовкам колонок.

        Нужно затем же, зачем чипы дублируют комбобокс: состояние, доступное
        только кликом мыши по 26-пиксельному заголовку, с клавиатуры не
        достать и в тестах не увидеть.
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
        """Какие колонки таблицы показывать (у EET это тоже пункт «Вид»).

        Ключ настройки — английская подпись колонки, а не её номер: вставь
        кто-нибудь колонку в середину, и номера сдвинулись бы, спрятав чужую.
        Переименованная подпись просто перестанет совпадать, и колонка вернётся
        видимой — из двух отказов этот безобиднее.
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
            # спрятать таблицу целиком — не настройка, а поломка
            hidden.discard(label)
            self.column_actions[column].setChecked(True)
            return
        settings.qsettings().setValue("view/hidden_columns", "|".join(sorted(hidden)))
        self.editor_screen.table.setColumnHidden(column, not visible)

    def _toggle_status_button(self, action_id: str, visible: bool) -> None:
        settings.qsettings().setValue(f"view/button_{action_id}", visible)
        widget = self.toolbar.widgetForAction(self.actions[action_id])
        if widget is not None:
            # прячем кнопку, а не действие: тот же QAction живёт в меню
            # «Перевод» и в контекстном меню таблицы, и там он нужен
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
        """Готовые наборы правил — радиогруппой, как тема и сортировка.

        Смена набора из меню пишет в глобальный слой: это выбор строгости
        вообще, а не настройка под конкретный мод. Тонкая правка отдельных
        правил живёт в окне Shift+F6 и умеет писать в слой проекта.
        """
        menu = parent.addMenu(translate("MainWindow", "Rule preset"))
        self._qa_preset_menu = menu
        # Разделитель отделяет рекомендуемый набор от остальных. Родитель у
        # него окно, а не меню: из меню он уходит и возвращается при каждой
        # смене проекта, и умереть вместе с ним ему нельзя.
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
        """Отметить действующий набор и поднять рекомендуемый наверх.

        Пункты переставляются `removeAction`/`addAction`, а не пересборкой
        меню. `QMenu.clear()` здесь нельзя: он **удаляет** действия, у которых
        меню же и родитель, — а пересоздавать их значило бы копить пункты в
        радиогруппе, ровно как предупреждает `_populate_menus`.

        Зовётся по сигналу `rules_state`, а тот приходит и при открытии, и при
        закрытии проекта, — поэтому пометка появляется и исчезает сама.
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
        """Показать текущий фильтр во всех его витринах разом.

        Фильтр по статусу ставится из пяти мест — комбобокс, чипы статус-бара,
        дерево файлов, сводка сканирования и меню. Раньше каждое место знало
        только про себя: чип загорался, лишь когда кликнули по самому чипу.
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

    # --- вид ---

    def _restore_view_settings(self) -> None:
        s = settings.qsettings()
        self.act_show_toolbar.setChecked(s.value("view/toolbar", True, type=bool))
        self.act_show_tree.setChecked(s.value("view/file_tree", True, type=bool))
        self.act_show_context.setChecked(s.value("view/context", True, type=bool))

        hidden = self._hidden_columns()
        for column, label in DATA_COLUMNS:
            # setChecked сам дёрнет toggled и спрячет колонку — второй раз
            # прятать её здесь не надо
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
        """Список клавиш собирается из спеки действий — врать он не может.

        Раскладка та же, что у ESP/ESM Translator. Раньше список был написан
        руками и отставал от кода при каждой правке меню.
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

    # --- проекты ---

    def show_start(self) -> None:
        """Вернуться к списку проектов, отпустив открытый проект.

        Соединение обязательно закрыть: `open_project` работает в режиме WAL,
        рядом с файлом живут `-wal`/`-shm`, и пока они держатся, файл проекта
        нельзя ни удалить, ни переместить. Раньше экран просто переключался, и
        проект, открытый при запуске, оставался занятым всё время, пока
        пользователь разглядывал список.
        """
        self._close_project()
        self.project_path = None
        self._update_window_title()
        self.start_screen.reload()
        self.stack.setCurrentWidget(self.start_screen)
        self.statusBar().showMessage(
            translate("MainWindow", "Choose or create a project"))

    def _delete_project(self, raw: str) -> None:
        """Удалить файл проекта по требованию стартового экрана."""
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
        box.setDefaultButton(keep_btn)      # опасное действие не должно быть по Enter
        also_backups = QCheckBox(
            translate("MainWindow", "Delete the backups next to it as well"))
        box.setCheckBox(also_backups)
        box.exec()
        if box.clickedButton() is not delete_btn:
            return

        if self.project_path is not None and self.project_path == path:
            self.show_start()               # закрывает соединение и снимает WAL
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
            # Обещали корзину — а Windows не берёт туда файл, который не влезает
            # в её квоту. Проект перевода весит сотни мегабайт, так что случай
            # живой. Молчать нельзя: человек пойдёт искать файл и не найдёт.
            QMessageBox.warning(
                self, translate("MainWindow", "Delete project"),
                fill(translate("MainWindow",
                               "The recycle bin did not accept the file, so it "
                               "was deleted permanently:\n%1\n\nUsually this "
                               "means the file is larger than the bin allows."),
                     "\n".join(str(p) for p in removed.bypassed_trash)))

    def _offer_right_pen(self, path: Path) -> Path:
        """Проект чужого загона — предложить перенести. Возвращает путь к файлу.

        Спрашиваем **до открытия**: открытый проект держит `-wal`, и переносить
        его было бы поздно — пришлось бы закрывать только что открытое.

        Срабатывает только внутри папки проектов. Файл проекта переносим, и его
        нарочно кладут рядом с модом или отдают другому человеку — приставать к
        такому значило бы самому стать той бедой, от которой защищаемся.
        """
        game_id = project.read_game(path)
        if game_id is None:
            return path
        try:
            pen_root = settings.projects_dir().resolve()
            here = path.resolve().parent
            target = settings.projects_pen(game_id)
            if here == target.resolve():
                return path             # уже в своём загоне
            if here == pen_root:
                where = None            # в корне загонов — тоже не на месте
            elif here.parent == pen_root and games.by_folder(here.name):
                where = games.by_folder(here.name)
            else:
                # либо проект живёт своей жизнью вне папки проектов, либо лежит
                # в папке, которую завёл человек. И то и другое — не наше дело
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

        # набор правил — до первого пересчёта замечаний: иначе таблица успеет
        # посчитать колонку «!» встроенными значениями, а не настройкой проекта
        rules_state.open_project(conn)

        has_units = conn.execute("SELECT 1 FROM units LIMIT 1").fetchone()
        self.editor_screen.set_session(conn)
        if not has_units:
            self.scan_current()
        # строки, где переводить нечего (одна разметка), не должны висеть
        # в непереведённых — в том числе в проектах прежних версий. Ровно один
        # раз на проект: иначе отменённая через Ctrl+Z уборка возвращалась бы
        # при следующем открытии.
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
        self.statusBar().clearMessage()      # убрать приглашение выбрать проект
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
            # журнал — в базу: иначе рядом остаётся `-wal` размером с проект,
            # и следующее открытие начинается с чтения этих мегабайт
            project.checkpoint(self.conn)
            self.conn.close()
            self.conn = None
        self.project_name = None
        self._update_window_title()
        rules_state.close_project()
        # действия проекта без проекта только сбивают с толку: раньше они
        # оставались включёнными и падали на пустом соединении
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

    # --- сервис ---

    def _update_status_bar(self) -> None:
        if self.conn is None:
            return
        stats = project_stats(self.conn, PROJECT_ID)
        self.stats_label.setText(format_status_bar(stats))
        self.chips.set_stats(stats)
        self._sync_issues_chip()
        self.chips.show()

    def _on_selection_changed(self, count: int) -> None:
        """Охват массовой операции виден до нажатия, а не после."""
        self.selection_label.setText(
            fill(translate("MainWindow", "Rows selected: %1"), count)
            if count > 1 else "")

    def _on_chip_filter(self, status_value: str) -> None:
        self.editor_screen.set_status_filter(status_value or None)

    def _toggle_only_issues(self) -> None:
        """Чип «!» — та же витрина, что галка панели и пункт меню.

        Через `QAction`, а не мимо него: у действия уже есть слот, который
        зовёт `set_only_issues` и обновляет остальные витрины, — иначе чип
        загорался бы, а галка на панели оставалась снятой.
        """
        self.act_only_issues.toggle()

    def _show_qa(self) -> None:
        """Полная проверка проекта отдельным отчётом.

        Повседневные замечания видны в колонке «!» таблицы, поэтому панель
        больше не занимает место на экране постоянно.
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
        """Окно настройки проверок. Работает и без открытого проекта.

        Без проекта нельзя посчитать срабатывания, но набор правил глобальный,
        и запретить его настройку до открытия мода было бы странно.
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
        """Подтвердить переводы строк, где автор мода правил только оформление."""
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
        """Сменить папку оригинала и сразу перечитать её.

        Без сканирования смена ничего не значит: строки в базе остаются от
        прежней папки. Поэтому предлагаем скан прямо здесь, а не оставляем
        проект в состоянии «путь новый, содержимое старое».
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

    def _change_languages(self) -> None:
        """Сменить языки проекта и, если тронута папка языка, сразу перечитать.

        Смена языка папки меняет, какие файлы сканер считает своими, — без
        сканирования проект остался бы в состоянии «язык новый, содержимое
        старое». Смена одного лишь языка текста файлов не касается, и звать
        скан незачем.
        """
        from pdxloc.gui.languages_dialog import LanguagesDialog

        if self.conn is None:
            return
        dlg = LanguagesDialog(self.conn, PROJECT_ID, self)
        needs_scan: list[bool] = []
        dlg.languagesChanged.connect(needs_scan.append)
        if not dlg.exec():
            return
        # набор правил зависит от языка перевода: русские правила гасятся
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
        """Одно окно на всю память переводов: записи, базы и сборка."""
        from pdxloc.gui.tm_window import TmWindow

        if self.conn is None:
            return
        window = TmWindow(self.conn, self)
        window.sources.sourcesChanged.connect(self._on_tm_sources_changed)
        window.build.databasesChanged.connect(self.context_bar.refresh)
        window.exec()
        self.editor_screen.refresh_current()

    def _glossary(self) -> None:
        """Окно глоссария: принятые термины и очередь кандидатов.

        Прогон статистики идёт по файлу проекта своим соединением, поэтому окну
        нужен путь, а не только соединение.
        """
        from pdxloc.gui.glossary_window import GlossaryWindow

        if self.conn is None or self.project_path is None:
            return
        window = GlossaryWindow(self.conn, self.project_path, self)
        # принятый термин обязан подсветиться в поле оригинала сразу, не дожидаясь
        # закрытия окна: переводчик принимает термин ровно потому, что видит его
        # в строке перед собой
        window.glossaryChanged.connect(self.editor_screen.detail.reload_glossary)
        window.exec()
        self.editor_screen.detail.reload_glossary()

    def _machine_translate_batch(self) -> None:
        """Пакетный машинный перевод: охват, оценка, прогон, сводка."""
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
        """Строки писал воркер своим соединением — перечитываем всё."""
        self.editor_screen.open_project(PROJECT_ID)
        self._update_status_bar()

    def _on_tm_sources_changed(self) -> None:
        """Набор баз меняется сразу — подсказки и шапка должны это увидеть."""
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
        """Окно «О программе». Оно же — уведомление об условиях распространения.

        Так просит само приложение к GPL-3.0 («How to Apply These Terms»): для
        программы с окнами уведомление об отсутствии гарантий показывают именно
        в about box, а не в консоли, которой у нас нет.

        Про Qt сказано здесь же, и это не вежливость: в портативной сборке Qt
        уезжает внутрь архива (93 МБ из 120), то есть мы его распространяем, а
        LGPL требует сообщить получателю, что библиотека там и под какой
        лицензией.
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

    # --- геометрия ---

    def _restore_geometry(self) -> None:
        geo = settings.qsettings().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 800)

    def closeEvent(self, event) -> None:
        settings.qsettings().setValue("geometry", self.saveGeometry())
        # Ширины колонок — рядом с геометрией и по той же причине: человек
        # подогнал таблицу под свой экран, и заставлять его делать это каждый
        # запуск незачем (в EET это `ColumnsSizes`).
        self.editor_screen.table.save_column_widths()
        self._close_project()
        super().closeEvent(event)

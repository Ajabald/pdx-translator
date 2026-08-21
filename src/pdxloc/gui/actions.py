"""Every command of the application in one table.

The rule the module exists for: **each command has exactly one home**, its entry
in the main menu. The toolbar and the table context menu show THE SAME `QAction`
objects rather than copies of their own.

It used to be otherwise. «Validate» existed three times over: a toolbar button (a
QAction of its own with no shortcut, only a tooltip saying «F10»), a context menu
entry (its own QAction with a real F10) and the «✓» column of the table. Fixing
one copy did not touch the others, the texts drifted apart, and four toolbar
buttons — «Find», «Next untranslated», «Validate», «Unvalidate» — had no menu
entry at all, so they could not be found from the keyboard. Thirteen row
operations, conversely, lived in the context menu alone and never appeared in the
main menu.

The menu layout is taken from ESP/ESM Translator, the tool this interface aligns
itself with (see `ett4/Lang.xml`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

# The translation context: in EET the row keys are named after the window as
# well («Options.», «Import.», «Principal.»), and Linguist groups its tree by it.
# Writing it as a literal is mandatory — lupdate does not allow a variable and
# loses the string in silence (checked by `test_i18n.py`).
CTX = "Actions"

SEP = None                      # разделитель в меню и на панели

# когда действие доступно
ALWAYS = "always"               # всегда, даже без открытого проекта
PROJECT = "project"             # только при открытом проекте
NEVER = "never"                 # заглушка на будущее — выключена всегда

# who owns an action and in what context its shortcut works.
#
# TABLE is for the shortcuts that argue with editing text and nothing else:
# Ctrl+C, Ctrl+V and Ctrl+Z inside the translation field must mean
# «copy/paste/undo typing» rather than an operation on a table row. Everything
# else — F7, F8, F10… — is meaningless in a text field, so it works across the
# whole window, as in EET where F10 fires wherever the cursor happens to be.
WINDOW = "window"               # окно целиком
TABLE = "table"                 # таблица строк и её потомки


@dataclass(frozen=True, slots=True)
class Act:
    id: str
    text: str
    keys: tuple[str, ...] = ()
    icon: str | None = None     # имя файла в gui/icons без расширения
    tip: str = ""
    checkable: bool = False
    scope: str = PROJECT
    owner: str = WINDOW


# --- the commands themselves ---

ACTIONS: tuple[Act, ...] = (
    # файл и проект как файл
    Act("projects", QT_TRANSLATE_NOOP("Actions","Projects…"), icon="projects", scope=ALWAYS,
        tip=QT_TRANSLATE_NOOP("Actions","Back to the project list")),
    Act("open", QT_TRANSLATE_NOOP("Actions","Open project…"), ("Ctrl+O",), icon="open",
        scope=ALWAYS),
    Act("save_as", QT_TRANSLATE_NOOP("Actions","Save project as…"), ("Ctrl+Shift+S",)),
    Act("import", QT_TRANSLATE_NOOP("Actions","Load translation from mod…"), ("Ctrl+I",),
        icon="import",
        tip=QT_TRANSLATE_NOOP("Actions","Take translations from ready localization files — "
                                   "someone else's translation of this mod, or your own "
                                   "edits made directly in the files")),
    Act("export", QT_TRANSLATE_NOOP("Actions","Write translation to mod…"), ("Ctrl+E",),
        icon="export"),
    Act("prefs", QT_TRANSLATE_NOOP("Actions","Preferences…"), icon="prefs", scope=ALWAYS),
    Act("quit", QT_TRANSLATE_NOOP("Actions","Quit"), scope=ALWAYS),

    # правка
    Act("copy_cell", QT_TRANSLATE_NOOP("Actions","Copy cell"), ("Ctrl+C",), icon="copy",
        owner=TABLE),
    Act("paste_ru", QT_TRANSLATE_NOOP("Actions","Paste into translation"), ("Ctrl+V",),
        icon="paste", owner=TABLE),
    Act("copy_key", QT_TRANSLATE_NOOP("Actions","Copy key")),
    Act("reset", QT_TRANSLATE_NOOP("Actions","Reset translation"), icon="reset"),
    Act("save_row", QT_TRANSLATE_NOOP("Actions","Save row translation"), ("Ctrl+S",),
        tip=QT_TRANSLATE_NOOP("Actions","Edits are saved anyway when you leave the row — "
                                   "this is just in case")),
    Act("undo", QT_TRANSLATE_NOOP("Actions","Undo last operation"), ("Ctrl+Z",), icon="undo",
        owner=TABLE,
        tip=QT_TRANSLATE_NOOP("Actions","Rolls back the last batch of edits. In the "
                                   "translation field Ctrl+Z still undoes typing")),

    # перевод
    Act("ru_eq_en", QT_TRANSLATE_NOOP("Actions","Translation = Original"), ("F8",),
        icon="ru-eq-en",
        tip=QT_TRANSLATE_NOOP("Actions","For names, numbers and anything untranslatable")),
    Act("from_tm", QT_TRANSLATE_NOOP("Actions","Fill from translation memory"), ("F7",),
        icon="from-tm"),
    Act("mt", QT_TRANSLATE_NOOP("Actions","Machine-translate the row"), ("Ctrl+M",),
        icon="mt",
        tip=QT_TRANSLATE_NOOP("Actions","Sends the original to the service set up in "
                                   "«File → Preferences». The result is marked "
                                   "«Machine (unchecked)»")),
    Act("apply_same", QT_TRANSLATE_NOOP("Actions","Apply to all rows with the same original"),
        ("Ctrl+F6",)),
    Act("validate", QT_TRANSLATE_NOOP("Actions","Validate"), ("F10",), icon="validate",
        tip=QT_TRANSLATE_NOOP("Actions","Mark the row as reviewed")),
    Act("unvalidate", QT_TRANSLATE_NOOP("Actions","Unvalidate"), ("Shift+F10",),
        icon="unvalidate",
        tip=QT_TRANSLATE_NOOP("Actions","Back to the «Translated» status")),
    Act("custom", QT_TRANSLATE_NOOP("Actions","Custom status"), ("Ctrl+F10",), icon="custom"),
    Act("ignore", QT_TRANSLATE_NOOP("Actions","Ignore"), ("Ctrl+Shift+F10",), icon="ignore",
        tip=QT_TRANSLATE_NOOP("Actions","Nothing to translate — a row of bare tags, say")),
    Act("next_untranslated", QT_TRANSLATE_NOOP("Actions","Next untranslated"), ("F4",),
        icon="next-untranslated"),
    Act("prev_row", QT_TRANSLATE_NOOP("Actions","Previous row"), ("Ctrl+Up",)),
    Act("next_row", QT_TRANSLATE_NOOP("Actions","Next row"), ("Ctrl+Down",)),
    Act("save_and_next", QT_TRANSLATE_NOOP("Actions","Save and go to next"),
        ("Ctrl+Return", "Ctrl+Enter")),

    # фильтры
    Act("find", QT_TRANSLATE_NOOP("Actions","Find row…"), ("Ctrl+F",), icon="find",
        tip=QT_TRANSLATE_NOOP("Actions","Puts the cursor in the search box")),
    Act("only_issues", QT_TRANSLATE_NOOP("Actions","Only with issues"), ("Ctrl+Shift+I",),
        icon="issues", checkable=True,
        tip=QT_TRANSLATE_NOOP("Actions","Show only rows the check has questions about")),
    Act("show_deleted", QT_TRANSLATE_NOOP("Actions","Show deleted"), checkable=True,
        tip=QT_TRANSLATE_NOOP("Actions","Rows whose keys are gone from the original")),
    Act("reset_filters", QT_TRANSLATE_NOOP("Actions","Reset filters"), ("Ctrl+Shift+R",),
        icon="filter-reset",
        tip=QT_TRANSLATE_NOOP("Actions","Drops the status, file and search filters. "
                                   "The sort order stays")),

    # вид
    Act("show_toolbar", QT_TRANSLATE_NOOP("Actions","Toolbar"), checkable=True, scope=ALWAYS),
    Act("show_tree", QT_TRANSLATE_NOOP("Actions","File tree"), checkable=True, scope=ALWAYS),
    Act("show_context", QT_TRANSLATE_NOOP("Actions","Languages and databases in the header"),
        checkable=True, scope=ALWAYS),

    # проект
    Act("scan", QT_TRANSLATE_NOOP("Actions","Scan"), ("F5",), icon="scan",
        tip=QT_TRANSLATE_NOOP("Actions","Re-read the original files and find changes")),
    Act("actualize_cosmetic", QT_TRANSLATE_NOOP("Actions","Actualize cosmetic edits…"),
        tip=QT_TRANSLATE_NOOP("Actions","Confirm translations of rows where the mod author "
                                   "only changed formatting")),
    Act("archive", QT_TRANSLATE_NOOP("Actions","Archive of old translations…")),
    Act("en_root", QT_TRANSLATE_NOOP("Actions","Change original folder…"),
        tip=QT_TRANSLATE_NOOP("Actions","If the mod was re-downloaded elsewhere, or the "
                                   "project came from another person")),
    Act("project_languages", QT_TRANSLATE_NOOP("Actions", "Project languages…"),
        tip=QT_TRANSLATE_NOOP("Actions", "Game folders (l_english) and the language "
                                         "the text is actually written in")),
    Act("open_file", QT_TRANSLATE_NOOP("Actions","Show original in Explorer")),

    # проверка — у EET проверки живут отдельным меню, и не зря: их три разных
    # действия, и в «Проекте» они тонули между сканом и архивом
    Act("qa", QT_TRANSLATE_NOOP("Actions","Check the whole project…"), ("F6",), icon="qa"),
    Act("qa_rules", QT_TRANSLATE_NOOP("Actions","Configure checks…"), ("Shift+F6",),
        icon="qa-rules", scope=ALWAYS,
        tip=QT_TRANSLATE_NOOP("Actions","Which rules are on, with what leniency, and how "
                                   "often they fire on this project")),
    Act("qa_ignores", QT_TRANSLATE_NOOP("Actions","Marked «not an error»…"),
        icon="qa-ignores",
        tip=QT_TRANSLATE_NOOP("Actions","Silenced issues — they can be put back into the "
                                   "check")),

    # инструменты
    Act("tm", QT_TRANSLATE_NOOP("Actions","Translation memory…"), ("F9",), icon="tm",
        tip=QT_TRANSLATE_NOOP("Actions","Memory entries, attached databases and building "
                                   "new ones — in a single window")),
    # Shift+F9 рядом с F9 по уже сложившемуся правилу окна-спутника: F6
    # проверка → Shift+F6 её настройка, F9 память → Shift+F9 глоссарий.
    Act("glossary", QT_TRANSLATE_NOOP("Actions","Glossary…"), ("Shift+F9",), icon="glossary",
        tip=QT_TRANSLATE_NOOP("Actions","Terms and candidates for them: statistics "
                                   "suggests, you accept")),
    Act("concordance", QT_TRANSLATE_NOOP("Actions","How was this translated before…"),
        ("Ctrl+Shift+F",), icon="concordance",
        tip=QT_TRANSLATE_NOOP("Actions","Search the memory for the selected piece of the "
                                   "original")),
    Act("open_bdd", QT_TRANSLATE_NOOP("Actions","Open databases folder"), icon="folder",
        scope=ALWAYS),
    Act("mt_batch", QT_TRANSLATE_NOOP("Actions","Machine translation…"), icon="mt",
        tip=QT_TRANSLATE_NOOP("Actions","Translate many rows at once through the "
                                   "service set up in «File → Preferences»")),

    # справка
    Act("shortcuts", QT_TRANSLATE_NOOP("Actions","Keyboard shortcuts"), scope=ALWAYS),
    Act("about", QT_TRANSLATE_NOOP("Actions","About"), scope=ALWAYS),
)

BY_ID: dict[str, Act] = {a.id: a for a in ACTIONS}

# «@имя» — порождаемое подменю (радиогруппа), его строит ActionRegistry
MENU: tuple[tuple[str, tuple[str | None, ...]], ...] = (
    (QT_TRANSLATE_NOOP("MainWindow", "&File"),
     ("projects", "open", "save_as", SEP, "import", "export",
      SEP, "prefs", SEP, "quit")),
    (QT_TRANSLATE_NOOP("MainWindow", "&Edit"),
     ("copy_cell", "paste_ru", "copy_key", "reset",
      SEP, "save_row", SEP, "undo")),
    (QT_TRANSLATE_NOOP("MainWindow", "&Translation"),
     ("ru_eq_en", "from_tm", "mt", "apply_same",
      SEP, "validate", "unvalidate", "custom", "ignore",
      SEP, "next_untranslated", "prev_row", "next_row", "save_and_next")),
    (QT_TRANSLATE_NOOP("MainWindow", "F&ilters"),
     ("find", SEP, "@status", SEP, "only_issues", "show_deleted",
      SEP, "reset_filters")),
    (QT_TRANSLATE_NOOP("MainWindow", "&View"),
     ("show_toolbar", "show_tree", "show_context",
      SEP, "@columns", "@buttons", SEP, "@sort", SEP, "@theme")),
    (QT_TRANSLATE_NOOP("MainWindow", "&Project"),
     ("scan", SEP, "actualize_cosmetic", "archive",
      SEP, "en_root", "project_languages", SEP, "open_file")),
    (QT_TRANSLATE_NOOP("MainWindow", "&Check"),
     ("qa", SEP, "@qa_preset", SEP, "qa_rules", "qa_ignores")),
    (QT_TRANSLATE_NOOP("MainWindow", "T&ools"),
     ("tm", "glossary", "concordance", SEP, "open_bdd", SEP, "mt_batch")),
    (QT_TRANSLATE_NOOP("MainWindow", "&Help"), ("shortcuts", "about")),
)

# Панель — витрина: всё, что здесь, обязано иметь пункт меню (см. тест
# test_toolbar_has_no_action_outside_menu). «Загрузить перевод из мода» в
# панель не идёт намеренно: операция редкая и разрушительная, ей место в меню.
TOOLBAR: tuple[str | None, ...] = (
    "scan", "export",
    SEP, "find", "only_issues", "reset_filters",
    SEP, "from_tm", "ru_eq_en",
    SEP, "validate", "unvalidate", "custom", "ignore",
    SEP, "next_untranslated",
    SEP, "qa", "qa_rules", "tm",
)

# Кнопки статуса панели: их видимость переключается в «Вид → Кнопки статуса»
# (приём EET). Прятать `QAction` нельзя — он один и тот же в меню, панели и
# контекстном меню; прячется именно кнопка панели.
STATUS_BUTTONS: tuple[str, ...] = ("validate", "unvalidate", "custom", "ignore")

CONTEXT: tuple[str | None, ...] = (
    "copy_cell", "paste_ru",
    SEP, "ru_eq_en", "apply_same", "from_tm", "mt",
    SEP, "validate", "unvalidate", "custom", "ignore",
    SEP, "reset",
    SEP, "copy_key", "concordance", "open_file",
)


@dataclass
class ActionRegistry:
    """Живые QAction по спеке: создание, включение, раскладка по витринам."""

    actions: dict[str, QAction] = field(default_factory=dict)

    def build(self, window, table) -> None:
        """Создать все действия. `table` — владелец действий над строками.

        The parent decides the context of a shortcut. Ctrl+Z, Ctrl+C and Ctrl+V
        have to belong to the table: a QAction of the main window defaults to the
        whole window as its context, and Qt consults its shortcut map before the
        event reaches the focused widget. Because of that, Ctrl+Z in the
        translation field used to undo not the typing but the last bulk operation
        of the project.
        """
        for spec in ACTIONS:
            owner = table if spec.owner == TABLE else window
            action = QAction(translate("Actions", spec.text), owner)
            if spec.keys:
                action.setShortcuts([QKeySequence(k) for k in spec.keys])
            if spec.owner == TABLE:
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                table.addAction(action)      # the shortcut works with no menu open
            if spec.checkable:
                action.setCheckable(True)
            self.actions[spec.id] = action
        self.retranslate()      # it also sets the tooltips, all in one place

    def retranslate(self) -> None:
        """Re-read the command texts in the current language.

        This one method is enough for three shop windows at once: the toolbar and
        the context menu show THE SAME QAction objects rather than copies of their
        own — exactly the property the registry exists for.
        """
        for spec in ACTIONS:
            action = self.actions.get(spec.id)
            if action is None:
                continue
            action.setText(translate("Actions", spec.text))
            if spec.tip:
                tip = translate("Actions", spec.tip)
                action.setToolTip(tip)
                action.setStatusTip(tip)

    # --- availability ---

    def __getitem__(self, action_id: str) -> QAction:
        return self.actions[action_id]

    def __iter__(self):
        return iter(self.actions.items())

    def connect(self, action_id: str, slot) -> QAction:
        action = self.actions[action_id]
        (action.toggled if BY_ID[action_id].checkable else action.triggered).connect(slot)
        return action

    def set_enabled(self, has_project: bool) -> None:
        """Project actions with no project only confuse — and used to fall over on an
        empty connection."""
        for spec in ACTIONS:
            if spec.scope == PROJECT:
                self.actions[spec.id].setEnabled(has_project)
            elif spec.scope == NEVER:
                self.actions[spec.id].setEnabled(False)

    # --- shop windows ---

    def fill_menu(self, menu, ids) -> None:
        for action_id in ids:
            if action_id is SEP:
                menu.addSeparator()
            else:
                menu.addAction(self.actions[action_id])

    def fill_toolbar(self, bar, ids) -> None:
        for action_id in ids:
            if action_id is SEP:
                bar.addSeparator()
            else:
                bar.addAction(self.actions[action_id])

    def check_group(self, menu, parent, items, on_toggle) -> dict:
        """A submenu of independent ticks: «Columns», «Status buttons».

        Not a radio group: any subset may be shown. It returns the entries keyed
        by value — the caller has to be able both to tick them, since the setting
        comes from QSettings, and to rename them when the language changes.
        """
        made: dict = {}
        for value, label in items:
            action = QAction(label, parent, checkable=True)
            # tick before subscribing: `toggled` while the menu is being built would call
            # the slot before the toolbar it reaches into has been assembled
            action.setChecked(True)
            action.toggled.connect(
                lambda checked, v=value: on_toggle(v, checked))
            menu.addAction(action)
            made[value] = action
        return made

    def radio_group(self, menu, parent, items, on_pick) -> dict:
        """A radio-group submenu: «Show», «Sort», «Theme».

        It returns the entries keyed by value — the caller needs to be able to
        mark the current choice when it is changed from elsewhere: by a chip, a
        column header or the preferences dialog.
        """
        group = QActionGroup(parent)
        group.setExclusive(True)
        made: dict = {}
        for value, label in items:
            action = QAction(label, parent, checkable=True)
            action.triggered.connect(lambda _=False, v=value: on_pick(v))
            group.addAction(action)
            menu.addAction(action)
            made[value] = action
        return made

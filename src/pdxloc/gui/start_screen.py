"""Стартовый экран: недавние проекты, создание и открытие файла проекта."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QBrush, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from pdxloc import settings
from pdxloc.core import games, languages as lang_mod
from pdxloc.core.i18n import fill, translate
from pdxloc.core.languages import PARADOX_LANGUAGES
from pdxloc.gui import shell, theme
from pdxloc.gui.widgets import HintLabel

CTX = "StartScreen"

# Оставлено ради внешнего кода, который импортировал список отсюда. Сам список
# переехал в ядро: справочник данных не место в модуле окна.
LANGUAGES = list(PARADOX_LANGUAGES)


def safe_name(name: str) -> str:
    """Имя файла из названия проекта: в названии бывает двоеточие и слэш."""
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .")


class ProjectDialog(QDialog):
    """Создание проекта: имя, папки оригинала и перевода, языки, файл проекта."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("StartScreen", "New project"))
        self.setMinimumWidth(640)

        form = QFormLayout(self)

        # Игра — первым полем: она задаёт и список языковых папок, и загон, в
        # который ляжет файл проекта. Спрашивать её после путей значило бы
        # предлагать папки, которых у игры нет.
        self.game_combo = QComboBox()
        self.game_combo.setEditable(True)      # своя игра — свободным именем
        for game_id in games.ORDER:
            self.game_combo.addItem(games.title(game_id), game_id)
        self.game_combo.setToolTip(translate(
            "StartScreen",
            "Format is the same across the series. Of another game — type its "
            "name: it gets a pen of its own next to the rest"))
        self.game_combo.currentTextChanged.connect(self._on_game_changed)
        form.addRow(translate("StartScreen", "Game:"), self.game_combo)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._suggest_file)
        form.addRow(translate("StartScreen", "Name:"), self.name_edit)

        self.src_edit = QLineEdit()
        self.tgt_edit = QLineEdit()
        for label, edit in (
                (translate("StartScreen", "Original folder:"), self.src_edit),
                (translate("StartScreen", "Translation folder:"), self.tgt_edit)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(edit, 1)
            btn = QToolButton()
            btn.setText(translate("StartScreen", "Browse…"))   # а не узкое «…»
            btn.setToolTip(translate("StartScreen", "Choose a folder"))
            btn.clicked.connect(lambda _, e=edit: self._browse_dir(e))
            row.addWidget(btn)
            form.addRow(label, row)
        self.src_edit.editingFinished.connect(self._suggest_target)

        langs = QHBoxLayout()
        self.src_lang = QComboBox()
        self.src_lang.setEditable(True)
        self.src_lang.addItems(LANGUAGES)
        self.src_lang.setCurrentText("english")
        self.src_lang.currentTextChanged.connect(self._update_hint)
        self.tgt_lang = QComboBox()
        self.tgt_lang.setEditable(True)
        self.tgt_lang.addItems(LANGUAGES)
        self.tgt_lang.setCurrentText("russian")
        self.tgt_lang.currentTextChanged.connect(self._update_hint)
        langs.addWidget(self.src_lang)
        langs.addWidget(QLabel("→"))
        langs.addWidget(self.tgt_lang)
        langs.addStretch(1)
        form.addRow(translate("StartScreen", "Game folders:"), langs)

        # Язык текста нужен редко — только при переводе на язык, которого в
        # игре нет. Поле, которое нечем заполнить, только путает, поэтому оно
        # скрыто до галки; поменять его можно и потом, в «Языках проекта».
        self.split = QCheckBox(translate(
            "StartScreen", "The text is in another language"))
        self.split.setToolTip(translate(
            "StartScreen",
            "Portuguese in CK3, say, lives in l_english files: the game has no "
            "folder of its own for it"))
        form.addRow(self.split)

        self.locales = QWidget()
        locales_row = QHBoxLayout(self.locales)
        locales_row.setContentsMargins(0, 0, 0, 0)
        self.src_locale = QComboBox()
        self.tgt_locale = QComboBox()
        for box in (self.src_locale, self.tgt_locale):
            box.setEditable(True)
            for code in lang_mod.TEXT_LOCALES:
                box.addItem(lang_mod.locale_name(code), code)
        locales_row.addWidget(self.src_locale)
        locales_row.addWidget(QLabel("→"))
        locales_row.addWidget(self.tgt_locale)
        locales_row.addStretch(1)
        self.locales.setVisible(False)
        self.split.toggled.connect(self._on_split_toggled)
        form.addRow(translate("StartScreen", "Text languages:"), self.locales)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.file_edit = QLineEdit()
        # по умолчанию проект ложится в папку Projects самого приложения, но
        # путь виден и правится: файл проекта переносим, его кладут и к моду
        self.file_edit.setPlaceholderText(
            str(settings.projects_dir() / f"<name>{settings.PROJECT_EXT}"))
        file_row.addWidget(self.file_edit, 1)
        file_btn = QToolButton()
        file_btn.setText(translate("StartScreen", "Browse…"))
        file_btn.setToolTip(translate(
            "StartScreen", "Choose where to put the project file"))
        file_btn.clicked.connect(self._browse_file)
        file_row.addWidget(file_btn)
        form.addRow(translate("StartScreen", "Project file:"), file_row)

        self.hint = HintLabel()
        form.addRow(self.hint)
        self._update_hint()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def game_id(self) -> str:
        """Игра из списка либо слаг своего имени."""
        text = self.game_combo.currentText().strip()
        index = self.game_combo.findText(text)
        if index >= 0 and self.game_combo.itemData(index):
            return str(self.game_combo.itemData(index))
        return games.slug(text) if text else games.CK3

    def game_title(self) -> str:
        return self.game_combo.currentText().strip() or games.title(games.CK3)

    def _on_game_changed(self) -> None:
        """Смена игры меняет и языковые папки, и загон под файл проекта."""
        allowed = games.languages(self.game_id())
        for box, keep in ((self.src_lang, "english"), (self.tgt_lang, "russian")):
            current = box.currentText().strip()
            box.blockSignals(True)
            box.clear()
            box.addItems(allowed)
            # выбор человека важнее списка: у игры может не быть его языка, но
            # моды заводят свои папки, и запрещать это нечем
            box.setCurrentText(current if current else keep)
            box.blockSignals(False)
        self._suggest_file(self.name_edit.text())
        self._update_hint()

    def _on_split_toggled(self, shown: bool) -> None:
        self.locales.setVisible(shown)
        if shown:
            # подставляем то, что и так подразумевается папками
            self.src_locale.setCurrentText(
                lang_mod.default_locale(self.src_lang.currentText().strip()))
            self.tgt_locale.setCurrentText(
                lang_mod.default_locale(self.tgt_lang.currentText().strip()))

    @staticmethod
    def _locale_code(box: QComboBox) -> str:
        text = box.currentText().strip()
        index = box.findText(text)
        if index >= 0 and box.itemData(index):
            return str(box.itemData(index))
        return text

    def _update_hint(self) -> None:
        """Подсказка и подсказки в полях путей идут за выбранными языками.

        Плейсхолдер — тот же совет, что и текст ниже, только короче; если он
        останется стоять на english→russian, пока подсказка говорит про polish,
        поле само себе противоречит.
        """
        src = self.src_lang.currentText().strip() or "english"
        tgt = self.tgt_lang.currentText().strip() or "russian"
        self.src_edit.setPlaceholderText(f"…\\localization\\{src}")
        self.tgt_edit.setPlaceholderText(f"…\\localization\\{tgt}")
        self.hint.setText(
            fill(translate(
                "StartScreen",
                "The original folder is the one holding *_l_%1.yml "
                "(for example …\\localization\\english).\n"
                "The translation folder is where *_l_%2.yml go; it may not "
                "exist yet.\nThe project file is portable: put it anywhere."),
                src, tgt))

    def _suggest_file(self, name: str) -> None:
        if name.strip():
            self.file_edit.setText(str(
                settings.projects_pen(self.game_id())
                / (safe_name(name) + settings.PROJECT_EXT)))

    def _suggest_target(self) -> None:
        """Подставить соседнюю папку языка перевода.

        У CK3 деревья языков лежат рядом: …\\localization\\english и
        …\\localization\\russian. Папки перевода при новом проекте обычно ещё
        нет, поэтому предлагаем путь, а не ищем существующий каталог.
        """
        src = self.src_edit.text().strip()
        if not src or self.tgt_edit.text().strip():
            return
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        src_path = Path(src)
        sibling = src_path.parent / tgt_lang if src_path.name != tgt_lang else src_path
        self.tgt_edit.setText(str(sibling))

    def _start_dir(self, edit: QLineEdit) -> str:
        """Откуда открывать проводник: текущее значение, иначе прошлый выбор."""
        return edit.text().strip() or settings.last_browse_dir()

    def _browse_dir(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("StartScreen", "Choose a folder"),
            self._start_dir(edit))
        if not path:
            return
        edit.setText(path)
        settings.set_last_browse_dir(path)
        if edit is self.src_edit:
            self._suggest_target()

    def _browse_file(self) -> None:
        current = self.file_edit.text().strip()
        if not current:
            name = safe_name(self.name_edit.text()) or "project"
            current = str(settings.projects_pen(self.game_id())
                          / (name + settings.PROJECT_EXT))
        settings.projects_pen(self.game_id()).mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, translate("StartScreen", "Project file"), current,
            fill(translate("StartScreen", "Translation project (*%1)"),
                 settings.PROJECT_EXT))
        if path:
            self.file_edit.setText(path)

    def _validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                translate("StartScreen", "Enter the project name."))
            return
        src = self.src_edit.text().strip()
        if not src or not Path(src).is_dir():
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                fill(translate("StartScreen",
                               "The original folder does not exist:\n%1"), src))
            return
        if not self.tgt_edit.text().strip():
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                translate("StartScreen", "Enter the translation folder."))
            return
        path = self._project_path()
        if path is None:
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                translate("StartScreen", "Enter the project file."))
            return
        if path.exists():
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                fill(translate("StartScreen", "The file already exists:\n%1"), path))
            return
        self.accept()

    def _project_path(self) -> Path | None:
        """Путь к файлу проекта. Голое имя без папки кладём в загон игры."""
        text = self.file_edit.text().strip()
        pen = settings.projects_pen(self.game_id())
        if not text:
            name = safe_name(self.name_edit.text())
            return pen / (name + settings.PROJECT_EXT) if name else None
        path = Path(text)
        if path.suffix != settings.PROJECT_EXT:
            path = path.with_suffix(settings.PROJECT_EXT)
        return path if path.parent != Path(".") else pen / path.name

    def values(self) -> dict:
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        # Пустая локаль означает «совпадает с папкой языка» — так и храним,
        # чтобы проект не зарастал значениями, которые и так выводятся.
        src_locale = tgt_locale = ""
        if self.split.isChecked():
            src_locale = self._locale_code(self.src_locale)
            tgt_locale = self._locale_code(self.tgt_locale)
            if src_locale == lang_mod.default_locale(src_lang):
                src_locale = ""
            if tgt_locale == lang_mod.default_locale(tgt_lang):
                tgt_locale = ""
        return {
            "path": self._project_path(),
            "name": self.name_edit.text().strip(),
            "game": self.game_id(),
            "src_root": self.src_edit.text().strip(),
            "tgt_root": self.tgt_edit.text().strip(),
            "src_lang": src_lang,
            "tgt_lang": tgt_lang,
            "src_locale": src_locale,
            "tgt_locale": tgt_locale,
        }


class StartScreen(QWidget):
    projectOpened = Signal(str)      # путь к файлу проекта
    # удаление отдаём наверх: экран не знает про открытое соединение, а файл
    # проекта нельзя стереть, пока он открыт
    deleteRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        layout.addWidget(self.title)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self._buttons: dict[str, QPushButton] = {}
        for key, slot in (
            ("create", self._create),
            ("open", self._open),
            ("open_file", self._open_file),
        ):
            btn = QPushButton()
            btn.clicked.connect(slot)
            row.addWidget(btn)
            self._buttons[key] = btn
        row.addSpacing(16)      # своё удаление отделено от повседневных кнопок
        for key, slot in (
            ("reveal", self._reveal),
            ("forget", self._forget),
            ("delete", self._delete),
        ):
            btn = QPushButton()
            btn.clicked.connect(slot)
            row.addWidget(btn)
            self._buttons[key] = btn
        row.addStretch(1)
        layout.addLayout(row)

        # Delete убирает из списка, Shift+Delete удаляет файл — как в проводнике
        self._act_forget = QAction(self)
        self._act_forget.setShortcut(QKeySequence.Delete)
        self._act_forget.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self._act_forget.triggered.connect(self._forget)
        self.list.addAction(self._act_forget)
        self._act_delete = QAction(self)
        self._act_delete.setShortcut(QKeySequence("Shift+Delete"))
        self._act_delete.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self._act_delete.triggered.connect(self._delete)
        self.list.addAction(self._act_delete)

        self.retranslate()
        self.reload()

    def retranslate(self) -> None:
        """Экран показывается между проектами и живёт всю сессию."""
        # вызов вынесен из f-строки: внутри неё lupdate строку не видит
        title = translate("StartScreen", "Translation projects")
        self.title.setText(f"<h2>{title}</h2>")
        labels = {
            "create": translate("StartScreen", "Create…"),
            "open": translate("StartScreen", "Open"),
            "open_file": translate("StartScreen", "Open file…"),
            "reveal": translate("StartScreen", "Show in Explorer"),
            "forget": translate("StartScreen", "Remove from the list"),
            "delete": translate("StartScreen", "Delete…"),
        }
        for key, text in labels.items():
            self._buttons[key].setText(text)
        self._act_forget.setText(labels["forget"])
        self._act_delete.setText(labels["delete"])
        self.reload()       # в строках списка есть «файл не найден»

    def _show_menu(self, pos) -> None:
        if self.list.itemAt(pos) is None:
            return
        menu = QMenu(self.list)
        menu.addAction(translate("StartScreen", "Open"), self._open)
        menu.addAction(translate("StartScreen", "Show in Explorer"), self._reveal)
        menu.addSeparator()
        menu.addAction(self._act_forget)
        menu.addAction(self._act_delete)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def reload(self) -> None:
        """Недавние проекты, сгруппированные по играм.

        Группы идут по свежести, а не по алфавиту: список недавних тем и ценен,
        что сверху лежит то, с чем работали вчера.

        Заголовки — такие же строки списка, только невыбираемые. `QTreeWidget`
        потребовал бы переписать и выбор, и контекстное меню, и `_selected_path`,
        а показывал бы то же самое.
        """
        self.list.clear()
        by_game: dict[str, list[dict]] = {}
        for item in settings.recent_projects():
            by_game.setdefault(settings.project_game_hint(item), []).append(item)

        for game_id, items in by_game.items():
            self.list.addItem(self._group_header(game_id))
            for item in items:
                self.list.addItem(self._project_item(item))
        self._select_first_project()

    def _group_header(self, game_id: str) -> QListWidgetItem:
        title = games.title(game_id) if game_id else translate(
            "StartScreen", "Game not specified")
        header = QListWidgetItem(title)
        header.setFlags(Qt.NoItemFlags)         # заголовок не выбирается
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        header.setForeground(QBrush(theme.qcolor("text.disabled")))
        return header

    @staticmethod
    def _project_item(item: dict) -> QListWidgetItem:
        path = Path(item["path"])
        total, done = item.get("total", 0), item.get("done", 0)
        pct = f" — {done}/{total} ({round(100 * done / total, 1)}%)" if total else ""
        entry = QListWidgetItem(f"{item.get('name') or path.stem}{pct}\n{path}")
        entry.setData(Qt.UserRole, str(path))
        if not path.is_file():
            entry.setForeground(QBrush(theme.qcolor("text.disabled")))
            missing = translate("StartScreen", "file not found")
            entry.setText(f"{item.get('name') or path.stem} — {missing}\n{path}")
        return entry

    def _select_first_project(self) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole):
                self.list.setCurrentRow(row)
                return

    def _selected_path(self) -> Path | None:
        item = self.list.currentItem()
        # у заголовка группы пути нет — и команды над ним бессмысленны
        value = item.data(Qt.UserRole) if item else None
        return Path(value) if value else None

    def create_project(self) -> None:
        """Создать проект — та же команда, что кнопкой, но вызываемая извне."""
        self._create()

    def _create(self) -> None:
        from pdxloc import project

        dlg = ProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        values = dlg.values()
        try:
            conn = project.create_project(
                values["path"], name=values["name"], game=values["game"],
                src_root=values["src_root"], tgt_root=values["tgt_root"],
                src_lang=values["src_lang"], tgt_lang=values["tgt_lang"],
                src_locale=values["src_locale"], tgt_locale=values["tgt_locale"])
            conn.close()
        except Exception as e:      # noqa: BLE001 — показываем пользователю
            QMessageBox.critical(
                self, translate("StartScreen", "Project"),
                fill(translate("StartScreen",
                               "Could not create the project:\n%1"), e))
            return
        settings.remember_project(values["path"], values["name"],
                                  game=values["game"])
        self.reload()
        self.projectOpened.emit(str(values["path"]))

    def _open(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        if not path.is_file():
            QMessageBox.warning(
                self, translate("StartScreen", "Project"),
                fill(translate("StartScreen", "Project file not found:\n%1"), path))
            return
        self.projectOpened.emit(str(path))

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, translate("StartScreen", "Open project"),
            str(settings.projects_dir()),
            fill(translate("StartScreen",
                           "Translation project (*%1);;All files (*)"),
                 settings.PROJECT_EXT))
        if path:
            self.projectOpened.emit(path)

    def _forget(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        answer = QMessageBox.question(
            self, translate("StartScreen", "Remove from the list"),
            fill(translate("StartScreen",
                           "Remove the project from the recent list?\n\n"
                           "The file %1 itself stays on disk."), path.name))
        if answer == QMessageBox.Yes:
            settings.forget_project(path)
            self.reload()

    def _reveal(self) -> None:
        path = self._selected_path()
        if path is not None:
            shell.reveal(path)

    def _delete(self) -> None:
        """Решение принимает главное окно: только оно знает, открыт ли проект."""
        path = self._selected_path()
        if path is not None:
            self.deleteRequested.emit(str(path))

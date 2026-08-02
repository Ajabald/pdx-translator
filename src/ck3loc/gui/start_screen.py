"""Стартовый экран: недавние проекты, создание и открытие файла проекта."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ck3loc import settings

# Языки локализации Paradox (список открытый — поле редактируемое)
LANGUAGES = [
    "english", "russian", "french", "german", "spanish", "braz_por",
    "polish", "turkish", "korean", "japanese", "simp_chinese",
]


def safe_name(name: str) -> str:
    """Имя файла из названия проекта: в названии бывает двоеточие и слэш."""
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .")


class ProjectDialog(QDialog):
    """Создание проекта: имя, папки оригинала и перевода, языки, файл проекта."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый проект")
        self.setMinimumWidth(640)

        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._suggest_file)
        form.addRow("Название:", self.name_edit)

        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("…\\localization\\english")
        self.tgt_edit = QLineEdit()
        self.tgt_edit.setPlaceholderText("…\\localization\\russian")
        for label, edit in (("Папка оригинала:", self.src_edit),
                            ("Папка перевода:", self.tgt_edit)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(edit, 1)
            btn = QToolButton()
            btn.setText("Обзор…")      # как в остальных окнах, а не узкое «…»
            btn.setToolTip("Выбрать папку")
            btn.clicked.connect(lambda _, e=edit: self._browse_dir(e))
            row.addWidget(btn)
            form.addRow(label, row)
        self.src_edit.editingFinished.connect(self._suggest_target)

        langs = QHBoxLayout()
        self.src_lang = QComboBox()
        self.src_lang.setEditable(True)
        self.src_lang.addItems(LANGUAGES)
        self.src_lang.setCurrentText("english")
        self.tgt_lang = QComboBox()
        self.tgt_lang.setEditable(True)
        self.tgt_lang.addItems(LANGUAGES)
        self.tgt_lang.setCurrentText("russian")
        self.tgt_lang.currentTextChanged.connect(self._update_hint)
        langs.addWidget(self.src_lang)
        langs.addWidget(QLabel("→"))
        langs.addWidget(self.tgt_lang)
        langs.addStretch(1)
        form.addRow("Языки:", langs)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.file_edit = QLineEdit()
        # по умолчанию проект ложится в папку Projects самого приложения, но
        # путь виден и правится: файл проекта переносим, его кладут и к моду
        self.file_edit.setPlaceholderText(
            str(settings.projects_dir() / f"<название>{settings.PROJECT_EXT}"))
        file_row.addWidget(self.file_edit, 1)
        file_btn = QToolButton()
        file_btn.setText("Обзор…")
        file_btn.setToolTip("Выбрать, куда положить файл проекта")
        file_btn.clicked.connect(self._browse_file)
        file_row.addWidget(file_btn)
        form.addRow("Файл проекта:", file_row)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #555;")
        form.addRow(self.hint)
        self._update_hint()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _update_hint(self) -> None:
        tgt = self.tgt_lang.currentText().strip() or "russian"
        self.hint.setText(
            f"Папка оригинала — та, где лежат *_l_{self.src_lang.currentText().strip()}.yml "
            f"(например …\\localization\\english).\n"
            f"Папка перевода — куда писать *_l_{tgt}.yml; её может ещё не быть.\n"
            f"Файл проекта переносим: его можно положить куда угодно.")

    def _suggest_file(self, name: str) -> None:
        if name.strip():
            self.file_edit.setText(str(settings.projects_dir() / (safe_name(name) + settings.PROJECT_EXT)))

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
        path = QFileDialog.getExistingDirectory(self, "Выбор папки", self._start_dir(edit))
        if not path:
            return
        edit.setText(path)
        settings.set_last_browse_dir(path)
        if edit is self.src_edit:
            self._suggest_target()

    def _browse_file(self) -> None:
        current = self.file_edit.text().strip()
        if not current:
            name = safe_name(self.name_edit.text()) or "проект"
            current = str(settings.projects_dir() / (name + settings.PROJECT_EXT))
        settings.projects_dir().mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Файл проекта", current,
            f"Проект перевода (*{settings.PROJECT_EXT})")
        if path:
            self.file_edit.setText(path)

    def _validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Проект", "Укажите название проекта.")
            return
        src = self.src_edit.text().strip()
        if not src or not Path(src).is_dir():
            QMessageBox.warning(self, "Проект", f"Папка оригинала не существует:\n{src}")
            return
        if not self.tgt_edit.text().strip():
            QMessageBox.warning(self, "Проект", "Укажите папку перевода.")
            return
        path = self._project_path()
        if path is None:
            QMessageBox.warning(self, "Проект", "Укажите файл проекта.")
            return
        if path.exists():
            QMessageBox.warning(self, "Проект", f"Файл уже существует:\n{path}")
            return
        self.accept()

    def _project_path(self) -> Path | None:
        """Путь к файлу проекта. Голое имя без папки кладём в Projects."""
        text = self.file_edit.text().strip()
        if not text:
            name = safe_name(self.name_edit.text())
            return settings.projects_dir() / (name + settings.PROJECT_EXT) if name else None
        path = Path(text)
        if path.suffix != settings.PROJECT_EXT:
            path = path.with_suffix(settings.PROJECT_EXT)
        return path if path.parent != Path(".") else settings.projects_dir() / path.name

    def values(self) -> dict:
        return {
            "path": self._project_path(),
            "name": self.name_edit.text().strip(),
            "src_root": self.src_edit.text().strip(),
            "tgt_root": self.tgt_edit.text().strip(),
            "src_lang": self.src_lang.currentText().strip() or "english",
            "tgt_lang": self.tgt_lang.currentText().strip() or "russian",
        }


class StartScreen(QWidget):
    projectOpened = Signal(str)      # путь к файлу проекта

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Проекты перевода</h2>"))

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        for text, slot in (
            ("Создать…", self._create),
            ("Открыть", self._open),
            ("Открыть файл…", self._open_file),
            ("Убрать из списка", self._forget),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for item in settings.recent_projects():
            path = Path(item["path"])
            total, done = item.get("total", 0), item.get("done", 0)
            pct = f" — {done}/{total} ({round(100 * done / total, 1)}%)" if total else ""
            entry = QListWidgetItem(f"{item.get('name') or path.stem}{pct}\n{path}")
            entry.setData(Qt.UserRole, str(path))
            if not path.is_file():
                entry.setForeground(QBrush(QColor("#999")))
                entry.setText(f"{item.get('name') or path.stem} — файл не найден\n{path}")
            self.list.addItem(entry)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _selected_path(self) -> Path | None:
        item = self.list.currentItem()
        return Path(item.data(Qt.UserRole)) if item else None

    def _create(self) -> None:
        from ck3loc import project

        dlg = ProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        values = dlg.values()
        try:
            conn = project.create_project(
                values["path"], name=values["name"],
                src_root=values["src_root"], tgt_root=values["tgt_root"],
                src_lang=values["src_lang"], tgt_lang=values["tgt_lang"])
            conn.close()
        except Exception as e:      # noqa: BLE001 — показываем пользователю
            QMessageBox.critical(self, "Проект", f"Не удалось создать проект:\n{e}")
            return
        settings.remember_project(values["path"], values["name"])
        self.reload()
        self.projectOpened.emit(str(values["path"]))

    def _open(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        if not path.is_file():
            QMessageBox.warning(self, "Проект", f"Файл проекта не найден:\n{path}")
            return
        self.projectOpened.emit(str(path))

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть проект", str(settings.projects_dir()),
            f"Проект перевода (*{settings.PROJECT_EXT});;Все файлы (*)")
        if path:
            self.projectOpened.emit(path)

    def _forget(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        answer = QMessageBox.question(
            self, "Убрать из списка",
            f"Убрать проект из списка недавних?\n\nСам файл {path.name} останется на диске.")
        if answer == QMessageBox.Yes:
            settings.forget_project(path)
            self.reload()

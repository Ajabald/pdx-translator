"""Создание базы памяти переводов из папок локализации.

Основной сценарий — собрать базу игры из ванильной локализации CK3, чтобы
строки, скопированные модами из игры, переводились автоматически.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QToolButton, QVBoxLayout,
)

from ck3loc import settings
from ck3loc.core import tm_import
from ck3loc.gui.start_screen import LANGUAGES


class _BuildWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            report = tm_import.build_tm_from_dirs(
                self.params["src_dir"], self.params["tgt_dir"], self.params["out"],
                name=self.params["name"], src_lang=self.params["src_lang"],
                tgt_lang=self.params["tgt_lang"], kind=self.params["kind"],
                progress_cb=self.progress.emit,
                should_cancel=lambda: self._cancel)
            self.finished.emit(report)
        except tm_import.TmBuildCancelled:
            self.cancelled.emit()
        except Exception as e:      # noqa: BLE001
            self.failed.emit(str(e))


class TmImportDialog(QDialog):
    def __init__(self, parent=None, *, src_lang="english", tgt_lang="russian"):
        super().__init__(parent)
        self.setWindowTitle("Создать базу переводов из папок")
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)   # поля не должны липнуть к краю
        layout.setSpacing(8)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        layout.addLayout(form)

        self.name_edit = QLineEdit()
        form.addRow("Название базы:", self.name_edit)

        self.src_edit = QLineEdit()
        self.tgt_edit = QLineEdit()
        for label, edit in (("Папка оригинала:", self.src_edit),
                            ("Папка перевода:", self.tgt_edit)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(edit, 1)
            btn = QToolButton()
            btn.setText("Обзор…")
            btn.setToolTip("Выбрать папку")
            btn.clicked.connect(lambda _, e=edit: self._browse(e))
            row.addWidget(btn)
            form.addRow(label, row)

        langs = QHBoxLayout()
        self.src_lang = QComboBox()
        self.src_lang.setEditable(True)
        self.src_lang.addItems(LANGUAGES)
        self.src_lang.setCurrentText(src_lang)
        self.tgt_lang = QComboBox()
        self.tgt_lang.setEditable(True)
        self.tgt_lang.addItems(LANGUAGES)
        self.tgt_lang.setCurrentText(tgt_lang)
        langs.addWidget(self.src_lang)
        langs.addWidget(QLabel("→"))
        langs.addWidget(self.tgt_lang)
        langs.addStretch(1)
        form.addRow("Языки:", langs)

        self.kind = QComboBox()
        self.kind.addItem("База игры (ванильная локализация)", "game")
        self.kind.addItem("Импорт чужого перевода", "import")
        form.addRow("Тип базы:", self.kind)

        hint = QLabel(
            "Для базы игры укажите папки локализации установленной CK3, например:\n"
            "…\\Crusader Kings III\\game\\localization\\english и …\\localization\\russian.\n"
            f"Готовая база появится в папке {settings.bdd_dir()}.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        layout.addWidget(hint)

        self.bar = QProgressBar()
        self.bar.hide()
        layout.addWidget(self.bar)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.hide()
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.buttons.button(QDialogButtonBox.Ok).setText("Создать базу")
        self.buttons.accepted.connect(self._run)
        self.buttons.rejected.connect(self.reject)
        self.cancel_btn = QPushButton("Прервать")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.buttons.addButton(self.cancel_btn, QDialogButtonBox.ActionRole)
        self.cancel_btn.hide()      # скрывать только после добавления в блок кнопок
        layout.addWidget(self.buttons)

        # путь можно и вписать руками — тогда тоже подсказываем папки
        self.src_edit.editingFinished.connect(self._on_src_edited)
        self.tgt_edit.editingFinished.connect(self._on_tgt_edited)

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выбор папки", edit.text())
        if not path:
            return
        edit.setText(path)
        if edit is self.src_edit:
            self._autodetect(Path(path))
        else:
            self._resolve_target()

    def _on_src_edited(self) -> None:
        text = self.src_edit.text().strip()
        if text and Path(text).is_dir():
            self._autodetect(Path(text))
        else:
            self._update_estimate()

    def _on_tgt_edited(self) -> None:
        self._resolve_target()

    def _resolve_target(self) -> None:
        """Спуститься в папку языка внутри выбранной папки перевода.

        Перевод-мод обычно кладут отдельным модом со своим деревом: у
        русификатора AGOT это `localization/russian` (перевод мода) рядом с
        `localization/replace/russian` (замена ванильных строк). Указывают при
        этом общий корень — и пар не находилось ни одной.
        """
        src, tgt = self.src_edit.text().strip(), self.tgt_edit.text().strip()
        if not src or not tgt or not Path(src).is_dir() or not Path(tgt).is_dir():
            self._update_estimate()
            return
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        try:
            best, scored = tm_import.resolve_target_dir(
                Path(src), Path(tgt), src_lang, tgt_lang)
        except OSError:
            self._update_estimate()
            return
        if best is not None and best != Path(tgt):
            self.tgt_edit.setText(str(best))
            self._update_estimate()
            self.status.setText(
                f"{self.status.text()} · взята вложенная папка перевода: {best.name}")
            return
        if best is None and len(scored) > 1:
            # нашли папки языка, но пар всё равно нет — покажем, что смотрели
            looked = ", ".join(f"{p.name} (0 пар)" for p, _ in scored[1:])
            self._update_estimate()
            self.status.setText(f"{self.status.text()} · проверены вложенные: {looked}")
            return
        self._update_estimate()

    def _autodetect(self, chosen: Path) -> None:
        """Подставить настоящие папки локализации.

        Пользователь естественно указывает корень игры или мода, а локализация
        лежит глубже (у CK3 — game\\localization\\english). Без этого пары не
        находятся вообще, а раньше приложение молча создавало пустую базу.
        """
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        src, tgt = tm_import.find_localization_dirs(chosen, src_lang, tgt_lang)
        if src is not None and src != chosen:
            self.src_edit.setText(str(src))
            self.status.setText(f"Найдена папка локализации: {src}")
        if tgt is not None and not self.tgt_edit.text().strip():
            self.tgt_edit.setText(str(tgt))
        self._resolve_target()

    def _update_estimate(self) -> None:
        """Показать, сколько файлов имеет пару, ещё до запуска."""
        src, tgt = self.src_edit.text().strip(), self.tgt_edit.text().strip()
        if not src or not tgt or not Path(src).is_dir() or not Path(tgt).is_dir():
            return
        try:
            paired, total = tm_import.count_pairs(
                Path(src), Path(tgt),
                self.src_lang.currentText().strip() or "english",
                self.tgt_lang.currentText().strip() or "russian")
        except OSError:
            return
        if total == 0:
            self.status.setText("В папке оригинала нет файлов локализации")
        elif paired == 0:
            self.status.setText(
                f"Файлов оригинала: {total}, но ни у одного нет пары в папке перевода — "
                f"проверьте, что указаны именно папки локализации")
        else:
            self.status.setText(f"Файлов оригинала: {total}, из них с парой: {paired}")

    def _run(self) -> None:
        name = self.name_edit.text().strip()
        src = self.src_edit.text().strip()
        if not name or not src:
            QMessageBox.warning(self, "База переводов",
                                "Укажите название базы и папку оригинала.")
            return
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        safe = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .")
        out = settings.bdd_dir() / f"{safe}_{src_lang}-{tgt_lang}{settings.TM_EXT}"
        if out.exists():
            answer = QMessageBox.question(
                self, "База переводов", f"Файл уже существует:\n{out}\n\nПерезаписать?")
            if answer != QMessageBox.Yes:
                return
        settings.bdd_dir().mkdir(parents=True, exist_ok=True)

        # заранее говорим, если собирать нечего: раньше в этом случае
        # молча создавалась пустая база, которую можно было подключить
        tgt_text = self.tgt_edit.text().strip()
        if tgt_text and Path(tgt_text).is_dir():
            best, scored = tm_import.resolve_target_dir(
                Path(src), Path(tgt_text), src_lang, tgt_lang)
            if best is not None and best != Path(tgt_text):
                self.tgt_edit.setText(str(best))     # нашли вложенную папку языка
                tgt_text = str(best)
            paired, total = tm_import.count_pairs(
                Path(src), Path(tgt_text), src_lang, tgt_lang)
            if paired == 0:
                looked = "\n".join(f"  {p} — 0 пар" for p, _ in scored)
                QMessageBox.warning(
                    self, "База переводов",
                    f"Ни один из {total} файлов оригинала не имеет пары в папке перевода.\n\n"
                    f"Проверены папки:\n{looked}\n\n"
                    f"Обычно это значит, что указан корень игры или мода, а нужны папки "
                    f"локализации — например:\n"
                    f"  …\\game\\localization\\{src_lang}\n"
                    f"  …\\game\\localization\\{tgt_lang}\n\n"
                    f"Перевод-мод хранит файлы в своём дереве: у русификаторов это "
                    f"обычно …\\localization\\{tgt_lang}, а рядом лежит "
                    f"…\\localization\\replace\\{tgt_lang} — замена ванильных строк, "
                    f"к строкам мода отношения не имеющая.")
                return
            if paired > 300:
                answer = QMessageBox.question(
                    self, "База переводов",
                    f"Будет обработано {paired} файлов — это может занять около "
                    f"{max(1, paired // 50)} секунд, а база займёт заметное место на диске.\n\n"
                    f"Продолжить?")
                if answer != QMessageBox.Yes:
                    return

        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.cancel_btn.show()
        self.bar.show()
        self._thread = QThread(self)
        self._worker = _BuildWorker({
            "src_dir": src, "tgt_dir": self.tgt_edit.text().strip() or None,
            "out": out, "name": name, "src_lang": src_lang, "tgt_lang": tgt_lang,
            "kind": self.kind.currentData(),
        })
        self._out_path = out
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        # Только связанные методы этого окна! Лямбда — не QObject, и PySide
        # вызывает её напрямую в потоке отправителя: обработчик трогал бы
        # виджеты из рабочего потока, а это намертво вешало окно на финише.
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        # Поток останавливаем его же сигналом, а не ожиданием из основного:
        # сообщение о завершении приходит ещё до выхода из run(), и wait()
        # здесь намертво вешал окно.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.start()

    def _on_cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.status.setText("Прерывание…")
        self._worker.cancel()

    def _on_cancelled(self) -> None:
        self.bar.hide()
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        self.status.setText("Сборка прервана — файл базы не создан")

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        self.status.setText(name)

    def _on_done(self, report) -> None:
        self.cancel_btn.hide()
        self.bar.setValue(self.bar.maximum())
        self.status.setText("Готово")
        lines = [report.summary_ru(), "", f"Файл: {self._out_path}"]
        if report.warnings:
            lines += ["", "Предупреждения парсера:"] + [f"  {w}" for w in report.warnings[:50]]
        self.report_box.setPlainText("\n".join(lines))
        self.report_box.show()

    def _on_failed(self, message: str) -> None:
        self.bar.hide()
        self.cancel_btn.hide()
        self.status.setText("")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        QMessageBox.critical(self, "База переводов", f"Не удалось создать базу:\n{message}")

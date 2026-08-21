"""The «Build a database» tab: from localisation folders or from the project.

The main case is building a game database from the vanilla localisation so that
rows the mods copied from the game get translated on their own. The second mode
exports the project's own translations for attaching to another project; that
used to be a separate menu command which opened nothing but a file dialog.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from pdxloc import project as project_mod
from pdxloc import settings
from pdxloc.core import games
from pdxloc.core.i18n import fill, translate
from pdxloc.core import tm_import
from pdxloc.core.languages import PARADOX_LANGUAGES as LANGUAGES
from pdxloc.gui.widgets import HintLabel

FROM_DIRS, FROM_PROJECT = 0, 1


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
                game=self.params["game"],
                progress_cb=self.progress.emit,
                should_cancel=lambda: self._cancel)
            self.finished.emit(report)
        except tm_import.TmBuildCancelled:
            self.cancelled.emit()
        except Exception as e:      # noqa: BLE001
            self.failed.emit(str(e))


class TmBuildTab(QWidget):
    statusChanged = Signal(str)
    databasesChanged = Signal()      # a new database appeared: refresh the lists

    def __init__(self, parent=None, *, src_lang="english", tgt_lang="russian",
                 conn: sqlite3.Connection | None = None):
        super().__init__(parent)
        self.conn = conn
        self._thread: QThread | None = None
        self._worker: _BuildWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)   # the fields must not stick to the edge
        layout.setSpacing(8)

        mode = QHBoxLayout()
        self.mode_dirs = QRadioButton(translate("TmBuild", "From localization folders"))
        self.mode_dirs.setChecked(True)
        self.mode_project = QRadioButton(translate("TmBuild", "From the current project translations"))
        self.mode_project.setEnabled(conn is not None)
        if conn is None:
            self.mode_project.setToolTip(translate("TmBuild", "An open project is needed"))
        mode.addWidget(self.mode_dirs)
        mode.addWidget(self.mode_project)
        mode.addStretch(1)
        layout.addLayout(mode)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_dirs_page(src_lang, tgt_lang))
        self.pages.addWidget(self._build_project_page())
        layout.addWidget(self.pages)
        self.mode_dirs.toggled.connect(self._on_mode_changed)

        self.bar = QProgressBar()
        self.bar.hide()
        layout.addWidget(self.bar)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.hide()
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("TmBuild", "Create the database"))
        self.buttons.accepted.connect(self._run)
        self.cancel_btn = QPushButton(translate("TmBuild", "Interrupt"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.buttons.addButton(self.cancel_btn, QDialogButtonBox.ActionRole)
        self.cancel_btn.hide()      # hide only after it is added to the button block
        layout.addWidget(self.buttons)

    def game_id(self) -> str:
        """The game chosen on the tab: one from the list, or the slug of a typed name."""
        text = self.game_combo.currentText().strip()
        index = self.game_combo.findText(text)
        if index >= 0 and self.game_combo.itemData(index):
            return str(self.game_combo.itemData(index))
        return games.slug(text) if text else games.CK3

    def _build_dirs_page(self, src_lang: str, tgt_lang: str) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        outer.addLayout(form)

        # The game comes first: it decides which pen the database lands in and what
        # mark it carries. With a project open we take it from there — building a
        # database for another game while sitting in a project is rare, but there is
        # nothing to forbid it for.
        self.game_combo = QComboBox()
        self.game_combo.setEditable(True)
        for game_id in games.ORDER:
            self.game_combo.addItem(games.title(game_id), game_id)
        self.game_combo.setCurrentText(games.title(
            project_mod.game(self.conn) if self.conn is not None else games.CK3))
        form.addRow(translate("TmBuild", "Game:"), self.game_combo)

        self.name_edit = QLineEdit()
        form.addRow(translate("TmBuild", "Database name:"), self.name_edit)

        self.src_edit = QLineEdit()
        self.tgt_edit = QLineEdit()
        for label, edit in ((translate("TmBuild", "Original folder:"), self.src_edit),
                            (translate("TmBuild", "Translation folder:"), self.tgt_edit)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(edit, 1)
            btn = QToolButton()
            btn.setText(translate("TmBuild", "Browse…"))
            btn.setToolTip(translate("TmBuild", "Choose a folder"))
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
        form.addRow(translate("TmBuild", "Languages:"), langs)

        self.kind = QComboBox()
        self.kind.addItem(
            translate("TmBuild", "Game database (vanilla localization)"), "game")
        self.kind.addItem(
            translate("TmBuild", "Import of someone else's translation"), "import")
        form.addRow(translate("TmBuild", "Database kind:"), self.kind)

        outer.addWidget(HintLabel(fill(translate(
            "TmBuild",
            "For a game database point at the localization folders of the "
            "installed CK3, for example:\n…\\Crusader Kings III\\game\\"
            "localization\\english and …\\localization\\russian.\n"
            "The finished database appears in the folder %1."),
            settings.bdd_dir())))

        # the path can be typed in too — then we suggest folders as well
        self.src_edit.editingFinished.connect(self._on_src_edited)
        self.tgt_edit.editingFinished.connect(self._on_tgt_edited)
        return page

    def _build_project_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        outer.addLayout(form)
        self.export_name = QLineEdit()
        form.addRow(translate("TmBuild", "Database name:"), self.export_name)
        outer.addWidget(HintLabel(fill(translate(
            "TmBuild",
            "Translated and reviewed rows of the project go into a separate "
            "database in the folder %1 — it can be attached to another project."),
            settings.bdd_dir())))
        return page

    # --- modes ---

    def _on_mode_changed(self, _checked: bool) -> None:
        from_dirs = self.mode_dirs.isChecked()
        self.pages.setCurrentIndex(FROM_DIRS if from_dirs else FROM_PROJECT)
        self.ok_button.setText(
            translate("TmBuild", "Create the database") if from_dirs
            else translate("TmBuild", "Export"))
        if not from_dirs and not self.export_name.text().strip() and self.conn:
            self.export_name.setText(project_mod.project_name(self.conn))

    def shutdown(self) -> None:
        """No timers of its own; the thread is stopped through is_busy/cancel."""

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def status_text(self) -> str:
        return self.status.text()

    def _set_status(self, text: str) -> None:
        self.status.setText(text)
        self.statusChanged.emit(text)

    # --- choosing folders ---

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("TmBuild", "Choose a folder"), edit.text())
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
        """Descend into the language folder inside the chosen translation folder.

        A translation is usually shipped as a mod of its own with a tree of its
        own: the AGOT Russian pack has `localization/russian` — the mod's
        translation — next to `localization/replace/russian`, which replaces the
        vanilla rows. People point at the common root, and not a single pair used
        to be found.
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
            self._set_status(
                self.status.text() + fill(translate(
                    "TmBuild", " · took the nested translation folder: %1"),
                    best.name))
            return
        if best is None and len(scored) > 1:
            # language folders were found but still no pairs: show what was looked at
            zero = translate("TmBuild", "(0 pairs)")
            looked = ", ".join(f"{p.name} {zero}" for p, _ in scored[1:])
            self._update_estimate()
            self._set_status(self.status.text() + fill(translate(
                "TmBuild", " · nested checked: %1"), looked))
            return
        self._update_estimate()

    def _autodetect(self, chosen: Path) -> None:
        """Fill in the real localisation folders.

        People naturally point at the root of a game or a mod, while the
        localisation lies deeper — in CK3 at game\\localization\\english. Without
        this no pairs are found at all, and the application used to create an
        empty database in silence.
        """
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        src, tgt = tm_import.find_localization_dirs(chosen, src_lang, tgt_lang)
        if src is not None and src != chosen:
            self.src_edit.setText(str(src))
            self._set_status(fill(translate(
                "TmBuild", "Localization folder found: %1"), src))
        if tgt is not None and not self.tgt_edit.text().strip():
            self.tgt_edit.setText(str(tgt))
        self._resolve_target()

    def _update_estimate(self) -> None:
        """Show how many files have a counterpart, before anything is started."""
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
            self._set_status(translate("TmBuild", "There are no localization files in the original folder"))
        elif paired == 0:
            self._set_status(
                fill(translate("TmBuild",
                               "Original files: %1, but none of them has a pair "
                               "in the translation folder — check that the "
                               "localization folders are the ones given"), total))
        else:
            self._set_status(fill(translate(
                "TmBuild", "Original files: %1, of them with a pair: %2"),
                total, paired))

    # --- the run ---

    def _run(self) -> None:
        if self.mode_project.isChecked():
            self._export_project()
        else:
            self._build_from_dirs()

    def _export_project(self) -> None:
        from pdxloc.core import tm_import as core_tm_import

        if self.conn is None:
            return
        name = self.export_name.text().strip() or project_mod.project_name(self.conn)
        row = self.conn.execute(
            "SELECT src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
        pen = settings.bdd_pen(project_mod.game(self.conn))
        out = pen / (
            f"{_safe_name(name)}_{row['src_lang']}-{row['tgt_lang']}{settings.TM_EXT}")
        if out.exists():
            answer = QMessageBox.question(
                self, translate("TmBuild", "Export"),
                fill(translate("TmBuild", "The file already exists:\n%1\n\nOverwrite?"), out))
            if answer != QMessageBox.Yes:
                return
        pen.mkdir(parents=True, exist_ok=True)
        try:
            report = core_tm_import.export_project_tm(self.conn, out, name=name)
        except Exception as e:      # noqa: BLE001
            QMessageBox.critical(
                self, translate("TmBuild", "Export"),
                fill(translate("TmBuild", "Could not export:\n%1"), e))
            return
        self._set_status(fill(translate(
            "TmBuild", "Translation pairs exported: %1"), report.pairs))
        self.report_box.setPlainText(fill(translate(
            "TmBuild", "Done: %1 translation pairs.\n\n%2"), report.pairs, out))
        self.report_box.show()
        self.databasesChanged.emit()

    def _build_from_dirs(self) -> None:
        name = self.name_edit.text().strip()
        src = self.src_edit.text().strip()
        if not name or not src:
            QMessageBox.warning(self, translate("TmBuild", "Translation database"),
                                translate("TmBuild", "Enter the database name and the original folder."))
            return
        src_lang = self.src_lang.currentText().strip() or "english"
        tgt_lang = self.tgt_lang.currentText().strip() or "russian"
        pen = settings.bdd_pen(self.game_id())
        out = pen / f"{_safe_name(name)}_{src_lang}-{tgt_lang}{settings.TM_EXT}"
        if out.exists():
            answer = QMessageBox.question(
                self, translate("TmBuild", "Translation database"),
                fill(translate("TmBuild", "The file already exists:\n%1\n\nOverwrite?"), out))
            if answer != QMessageBox.Yes:
                return
        pen.mkdir(parents=True, exist_ok=True)

        # say in advance when there is nothing to build: the application used to create
        # an empty database in silence, and it could then be attached
        tgt_text = self.tgt_edit.text().strip()
        if tgt_text and Path(tgt_text).is_dir():
            best, scored = tm_import.resolve_target_dir(
                Path(src), Path(tgt_text), src_lang, tgt_lang)
            if best is not None and best != Path(tgt_text):
                self.tgt_edit.setText(str(best))     # a nested language folder was found
                tgt_text = str(best)
            paired, total = tm_import.count_pairs(
                Path(src), Path(tgt_text), src_lang, tgt_lang)
            if paired == 0:
                zero = translate("TmBuild", "— 0 pairs")
                looked = "\n".join(f"  {p} {zero}" for p, _ in scored)
                QMessageBox.warning(
                    self, translate("TmBuild", "Translation database"),
                    fill(translate(
                        "TmBuild",
                        "None of the %1 original files has a pair in the "
                        "translation folder.\n\nFolders checked:\n%2\n\n"
                        "Usually this means the game or mod root was given while "
                        "localization folders are needed — for example:\n"
                        "  …\\game\\localization\\%3\n"
                        "  …\\game\\localization\\%4\n\n"
                        "A translation mod keeps files in its own tree: for "
                        "Russian translations that is usually "
                        "…\\localization\\%4, and next to it lies "
                        "…\\localization\\replace\\%4 — a replacement of vanilla "
                        "strings, unrelated to the mod's own strings."),
                        total, looked, src_lang, tgt_lang))
                return
            if paired > 300:
                answer = QMessageBox.question(
                    self, translate("TmBuild", "Translation database"),
                    fill(translate(
                        "TmBuild",
                        "%1 files will be processed — this may take about %2 "
                        "seconds, and the database will take noticeable disk "
                        "space.\n\nContinue?"), paired, max(1, paired // 50)))
                if answer != QMessageBox.Yes:
                    return

        self.ok_button.setEnabled(False)
        self.cancel_btn.show()
        self.bar.show()
        self._thread = QThread(self)
        self._worker = _BuildWorker({
            "src_dir": src, "tgt_dir": self.tgt_edit.text().strip() or None,
            "out": out, "name": name, "src_lang": src_lang, "tgt_lang": tgt_lang,
            "kind": self.kind.currentData(), "game": self.game_id(),
        })
        self._out_path = out
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        # Bound methods of this widget only! A lambda is not a QObject, and PySide
        # calls it directly on the sender's thread: the handler would touch widgets
        # from the worker thread, and that hung the window for good at the finish.
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        # The thread is stopped by its own signal rather than by waiting from the main
        # one: the finished message arrives before run() returns, and wait() here hung
        # the window for good.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.start()

    def cancel_build(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self._set_status(translate("TmBuild", "Interrupting…"))
        self.cancel_build()

    def _on_cancelled(self) -> None:
        self.bar.hide()
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.ok_button.setEnabled(True)
        self._set_status(translate("TmBuild", "Build interrupted — the database file was not created"))

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        self._set_status(name)

    def _on_done(self, report) -> None:
        self.cancel_btn.hide()
        self.ok_button.setEnabled(True)
        self.bar.setValue(self.bar.maximum())
        self._set_status(translate("TmBuild", "Done"))
        lines = [report.summary(), "",
                 fill(translate("TmBuild", "File: %1"), self._out_path)]
        if report.warnings:
            lines += ["", translate("TmBuild", "Parser warnings:")] + [f"  {w}" for w in report.warnings[:50]]
        self.report_box.setPlainText("\n".join(lines))
        self.report_box.show()
        self.databasesChanged.emit()

    def _on_failed(self, message: str) -> None:
        self.bar.hide()
        self.cancel_btn.hide()
        self._set_status("")
        self.ok_button.setEnabled(True)
        QMessageBox.critical(
            self, translate("TmBuild", "Translation database"),
            fill(translate("TmBuild", "Could not create the database:\n%1"), message))


def _safe_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .")

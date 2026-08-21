"""Loading a translation from a ready localisation tree.

The preview is mandatory: the operation changes thousands of rows at once, and
before the button is pressed it must be visible how many rows and what will
become of them. What gets written goes as one batch and comes back with one
Ctrl+Z.

**The tree is read once per chosen folder.** The import rules — the checkboxes —
do not change the files on disk; they change the selection only, so toggling one
recomputes the plan over the already parsed tree, in memory. Every checkbox used
to walk the whole mod again, and pressing the button walked it twice more.

There is deliberately no thread here. The slow part used to be writing — a
`commit` per row cost one fsync per row — and that is now batched: a hundred
thousand rows go in seconds. Reading, once cached, happens exactly once per
chosen folder and costs about a second even on a large mod. A thread for that
would mean background work outliving a modal window, and the price is higher than
the gain.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_import, unit_ops
from pdxloc.core.loc_import import ImportOptions, ParsedTree


class ImportDialog(QDialog):
    imported = Signal()      # rows changed: refresh the table and the counters

    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.setWindowTitle(translate("Import", "Load translation from mod"))
        self.setMinimumWidth(640)

        self._tree: ParsedTree | None = None    # the parsed tree of the chosen folder
        self._plan: loc_import.ImportPlan | None = None

        proj = conn.execute(
            "SELECT ru_root, tgt_lang FROM projects WHERE id = ?", (project_id,)).fetchone()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(translate(
            "Import",
            "Take translations from a folder with ready localization files — "
            "someone else's translation of this mod, say, or your own edits "
            "made directly in the files."))
        intro.setWordWrap(True)      # otherwise the window stretches across the screen
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Import", "Translation folder:")))
        self.path_edit = QLineEdit(proj["ru_root"])
        row.addWidget(self.path_edit, 1)
        browse = QPushButton(translate("Import", "Browse…"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self.overwrite = QCheckBox(translate("Import", "Overwrite existing translations"))
        self.overwrite.setToolTip(
            translate("Import",
                      "Off — only rows that have no translation yet are taken"))
        layout.addWidget(self.overwrite)
        self.skip_equal = QCheckBox(translate(
            "Import", "Do not take rows where the translation equals the original"))
        self.skip_equal.setChecked(True)
        layout.addWidget(self.skip_equal)

        # The checkboxes never touch the disk: only the plan is recomputed over the
        # already parsed tree.
        for w in (self.overwrite, self.skip_equal):
            w.toggled.connect(self._preview)
        self.path_edit.editingFinished.connect(self._reread)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("Import", "Take the translations"))
        self.buttons.accepted.connect(self._run)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._reread()

    # --- internals ---

    def _options(self) -> ImportOptions:
        return ImportOptions(overwrite=self.overwrite.isChecked(),
                             skip_equal_to_source=self.skip_equal.isChecked())

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("Import", "Translation folder"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)
            self._reread()

    def _rel_paths(self) -> list[str]:
        return [r["rel_path"] for r in self.conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
            "ORDER BY rel_path", (self.project_id,))]

    # --- reading the tree ---

    def _reread(self) -> None:
        """Parse the chosen folder — the only place here that touches the disk.

        Called when the window opens and when the folder changes. The import
        rules never reach this point: they do not affect which files are found.
        """
        from pdxloc.project import languages as project_languages

        self._tree = self._plan = None
        folder = Path(self.path_edit.text().strip() or ".")
        langs = project_languages(self.conn, self.project_id)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._tree = loc_import.read_tree(
                folder, self._rel_paths(), langs.src_lang, langs.tgt_lang)
        except (FileNotFoundError, OSError) as e:
            self.report_box.setPlainText(str(e))
            self.ok_button.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._preview()

    # --- the plan and applying it ---

    def _preview(self) -> None:
        """Recompute the plan over the parsed tree. Never touches the disk."""
        if self._tree is None:
            return
        self._plan = loc_import.build_plan(
            self.conn, self.project_id, self._tree, self._options())
        report = self._plan.report
        lines = [report.summary()]
        if report.samples:
            lines += ["", translate("Import", "What will change (first rows):")]
            empty = translate("Import", "(empty)")
            lines += [f"  {key}: {(before or empty)[:60]} → {after[:60]}"
                      for key, before, after in report.samples[:20]]
        if report.warnings:
            lines += ["", fill(translate("Import", "Parser warnings: %1"),
                               len(report.warnings))]
        self.report_box.setPlainText("\n".join(lines))
        self.ok_button.setEnabled(report.imported > 0)

    def _run(self) -> None:
        if self._plan is None or not self._plan.changes:
            return
        answer = QMessageBox.question(
            self, translate("Import", "Loading a translation"),
            fill(translate("Import",
                           "Take %1 rows from the chosen folder?\n\nThe operation "
                           "is recorded as a single batch — it can be undone as a "
                           "whole via «Edit → Undo last operation» (Ctrl+Z)."),
                 self._plan.report.imported))
        if answer != QMessageBox.Yes:
            return

        batch = unit_ops.new_batch_id()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = loc_import.apply_plan(self.conn, self._plan, batch_id=batch)
        except (OSError, sqlite3.Error) as e:
            QMessageBox.critical(
                self, translate("Import", "Loading a translation"),
                fill(translate("Import", "Nothing was taken — the write failed:\n%1"), e))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.report_box.setPlainText(
            report.summary() + translate("Import", "\n\nDone. Undo it all with Ctrl+Z."))
        self.ok_button.setEnabled(False)
        self._plan = None            # there is nothing left to apply a second time
        self.imported.emit()

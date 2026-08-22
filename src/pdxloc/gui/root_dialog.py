"""Changing the folders of an existing project: the original and the translation.

The preview is mandatory for the same reason as in loading a translation: a
mistake in the path quietly turns the whole translation into archive on the next
scan. Before the button is pressed it must be visible how many of the files the
database knows were found in the new folder.

The two windows are alike but not the same: an original folder with no familiar
files is almost always a wrong path, while a translation folder with none is the
ordinary state of a mod nobody has translated yet — there the emptiness is what
the write is for.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from pdxloc.core.i18n import fill, translate
from pdxloc.core import relocate


class EnRootDialog(QDialog):
    rootChanged = Signal()      # the path is written; the project needs a scan

    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.preview: relocate.RootPreview | None = None
        self.setWindowTitle(translate("RootDialog", "Change the original folder"))
        self.setMinimumWidth(640)

        current = relocate.get_en_root(conn, project_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(translate(
            "RootDialog",
            "The folder the original is read from. It needs changing if the mod "
            "was re-downloaded elsewhere, the game library was moved, or the "
            "project came from another person."))
        intro.setWordWrap(True)      # otherwise the window stretches across the whole screen
        layout.addWidget(intro)

        now_label = QLabel(fill(translate("RootDialog", "Now: %1"), current))
        now_label.setWordWrap(True)
        now_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(now_label)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("RootDialog", "New folder:")))
        self.path_edit = QLineEdit(str(current))
        self.path_edit.editingFinished.connect(self._refresh)
        row.addWidget(self.path_edit, 1)
        browse = QPushButton(translate("RootDialog", "Browse…"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("RootDialog", "Change the folder"))
        self.buttons.accepted.connect(self._apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._refresh()

    # --- internals ---

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("RootDialog", "Original folder"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)
            self._refresh()

    def _refresh(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.preview = relocate.preview_root_change(
                self.conn, self.project_id, self.path_edit.text())
        except OSError as e:
            self.preview = None
            self.report_box.setPlainText(fill(translate(
                "RootDialog", "Could not read the folder:\n%1"), e))
            self.ok_button.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.report_box.setPlainText(self.preview.summary())
        same = (self.preview.root is not None
                and self.preview.root == relocate.get_en_root(self.conn, self.project_id))
        self.ok_button.setEnabled(self.preview.usable and not same)

    def _apply(self) -> None:
        if self.preview is None or not self.preview.usable:
            return
        p = self.preview
        if p.risky or not p.matched:
            lost = (fill(translate(
                "RootDialog",
                "\n\nRows that will become deleted: %1"
                "\nTranslations that go to the archive: %2"),
                p.units_missing, p.translated_missing) if p.units_missing else "")
            answer = QMessageBox.question(
                self, translate("RootDialog", "Change of the original folder"),
                fill(translate(
                    "RootDialog",
                    "The new folder holds %1 files out of the %2 the database "
                    "knows.%3\n\nTranslations are not deleted: they stay in the "
                    "archive and in the translation memory. Change the folder?"),
                    len(p.matched), p.known_files, lost))
            if answer != QMessageBox.Yes:
                return
        relocate.set_en_root(self.conn, self.project_id, p.root)
        self.rootChanged.emit()
        self.accept()


class TranslationRootDialog(QDialog):
    """Where the translation is read from and written into.

    Until 0.1.2 the folder was set when the project was created and could not be
    changed at all: a mistake made in the very first window stayed for the life
    of the project, and the write went on offering the wrong place.
    """

    rootChanged = Signal()      # the path is written; the project needs a scan

    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.preview: relocate.TargetPreview | None = None
        self.setWindowTitle(translate("RootDialog", "Change the translation folder"))
        self.setMinimumWidth(640)

        current = relocate.get_ru_root(conn, project_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(translate(
            "RootDialog",
            "The folder the translation is read from at a scan and written into "
            "at a write. It may be left empty: the mod has no translation yet, "
            "and the folder is asked for at the first write."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        now_label = QLabel(fill(translate("RootDialog", "Now: %1"), current)
                           if current is not None
                           else translate("RootDialog", "Now: not chosen"))
        now_label.setWordWrap(True)
        now_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(now_label)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("RootDialog", "New folder:")))
        self.path_edit = QLineEdit(str(current) if current is not None else "")
        self.path_edit.editingFinished.connect(self._refresh)
        row.addWidget(self.path_edit, 1)
        browse = QPushButton(translate("RootDialog", "Browse…"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("RootDialog", "Change the folder"))
        self.buttons.accepted.connect(self._apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._refresh()

    # --- internals ---

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("RootDialog", "Translation folder"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)
            self._refresh()

    def _refresh(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.preview = relocate.preview_target_change(
                self.conn, self.project_id, self.path_edit.text())
        except OSError as e:
            self.preview = None
            self.report_box.setPlainText(fill(translate(
                "RootDialog", "Could not read the folder:\n%1"), e))
            self.ok_button.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.report_box.setPlainText(self.preview.summary())
        current = relocate.get_ru_root(self.conn, self.project_id)
        chosen = None if self.preview.cleared else self.preview.chosen
        self.ok_button.setEnabled(self.preview.usable and chosen != current)

    def _apply(self) -> None:
        if self.preview is None or not self.preview.usable:
            return
        p = self.preview
        if p.cleared:
            answer = QMessageBox.question(
                self, translate("RootDialog", "Change of the translation folder"),
                translate(
                    "RootDialog",
                    "The project will be left without a translation folder. "
                    "Nothing is deleted: the translation stays in the project, "
                    "and the folder is asked for at the first write. Continue?"))
            if answer != QMessageBox.Yes:
                return
        relocate.set_ru_root(self.conn, self.project_id,
                             None if p.cleared else p.chosen)
        self.rootChanged.emit()
        self.accept()

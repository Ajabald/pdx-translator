"""Writing the translation into the mod files.

The output folder is kept in the project separately from `ru_root`: that one is
the import source, and writing over it by default would overwrite the very tree
the rows were read from.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QVBoxLayout,
)

from pdxloc import project as project_mod
from pdxloc.core.i18n import fill, translate
from pdxloc.core.exporter import TRANSLATED_STATUSES, export_project
from pdxloc.core.models import ExportOptions
from pdxloc.gui import prefs
from pdxloc.gui.widgets import HintLabel, WarningLabel


class ExportDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.setWindowTitle(translate("Export", "Writing the translation to mod files"))
        self.setMinimumWidth(600)

        proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        layout = QVBoxLayout(self)

        counts = conn.execute(
            f"""SELECT SUM(status IN ({','.join('?' * len(TRANSLATED_STATUSES))})
                           AND ru_text IS NOT NULL) AS exportable,
                       SUM(status = 'ignored') AS ignored,
                       SUM(status = 'machine') AS machine
                FROM units u JOIN files f ON f.id = u.file_id
                WHERE f.project_id = ? AND u.is_deleted = 0""",
            (*TRANSLATED_STATUSES, project_id),
        ).fetchone()
        from pdxloc.core.stats import project_stats
        stats = project_stats(conn, project_id)
        total = stats.total
        translated = counts["exportable"] or 0

        note = (fill(translate("Export", " · ignored: %1"), counts["ignored"])
                if counts["ignored"] else "")
        summary = QLabel(fill(translate(
            "Export", "Rows in total: %1, going to the mod: %2, "
                      "without a translation: %3%4"),
            total, translated, total - translated, note))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.radio_translated = QRadioButton(fill(translate(
            "Export", "Translated only (%1 rows)"), translated))
        self.radio_all = QRadioButton(fill(translate(
            "Export", "All rows — untranslated ones stay in English (%1 rows)"),
            total))
        self.radio_translated.setChecked(True)
        layout.addWidget(self.radio_translated)
        layout.addWidget(self.radio_all)

        self.stale_check = QCheckBox(translate("Export", "Include outdated translations (EN changed)"))
        self.stale_check.setChecked(True)
        layout.addWidget(self.stale_check)

        # The only gate machine translation leaves through. Closed by default:
        # what nobody has read must not reach players merely because someone
        # failed to clear a checkbox.
        machine = counts["machine"] or 0
        self.machine_check = QCheckBox(
            fill(translate("Export",
                           "Include machine translations, %1 rows "
                           "(nobody has checked them)"), machine)
            if machine else
            translate("Export",
                      "Include machine translations (nobody has checked them)"))
        self.machine_check.setEnabled(bool(machine))
        self.machine_check.setChecked(prefs.get("export/include_machine"))
        self.machine_check.toggled.connect(self._on_machine_toggled)
        layout.addWidget(self.machine_check)
        self.machine_warning = WarningLabel(translate(
            "Export",
            "Machine translation has been read by no one. In the game it can "
            "be wrong in meaning, break tooltips or lose icons."))
        self.machine_warning.setWordWrap(True)
        self.machine_warning.setVisible(self.machine_check.isChecked())
        layout.addWidget(self.machine_warning)

        self.backup_check = QCheckBox(translate("Export", "Back up the files being overwritten"))
        self.backup_check.setChecked(True)
        self.backup_check.setToolTip(
            translate("Export",
                      "Previous versions go into the backups folder — outside "
                      "the localization tree, otherwise the game would read the "
                      "copies as if they were real files"))
        layout.addWidget(self.backup_check)

        # `None` when the project was created without a translation folder — a mod
        # that is English only. The field then starts empty and the folder chosen
        # here becomes the translation folder of the project.
        self.ru_root = project_mod.translation_root_of(proj["ru_root"])
        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Export", "Mod folder:")))
        self.path_edit = QLineEdit(
            project_mod.get_export_root(conn)
            or (str(self.ru_root) if self.ru_root else ""))
        row.addWidget(self.path_edit, 1)
        browse = QPushButton(translate("Export", "Browse…"))
        browse.setToolTip(translate(
            "Export", "Choose a folder — the mod folder in Documents, say"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        langs = project_mod.languages(conn, project_id)
        self.src_lang, self.tgt_lang = langs.src_lang, langs.tgt_lang
        self.path_edit.textChanged.connect(self._update_preview)
        self.preview = HintLabel()
        layout.addWidget(self.preview)
        self.warning = WarningLabel()
        layout.addWidget(self.warning)
        self._update_preview()

        last = project_mod.get_last_export_at(conn)
        if last:
            layout.addWidget(HintLabel(fill(translate(
                "Export", "Last write: %1"), last)))

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.hide()
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.buttons.button(QDialogButtonBox.Ok).setText(
            translate("Export", "Write"))
        self.buttons.accepted.connect(self._run)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_machine_toggled(self, checked: bool) -> None:
        """The warning is shown at once, not as a modal before writing.

        The modal there is already taken by the overwrite warning, and a second
        one in a row gets dismissed unread. Here it stands next to the checkbox
        itself — at the moment the decision is made.
        """
        self.machine_warning.setVisible(checked)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, translate("Export", "Mod folder"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _update_preview(self) -> None:
        """Show what the file will be named and what will stand in its header."""
        row = self.conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
            "ORDER BY rel_path LIMIT 1", (self.project_id,)).fetchone()
        text = self.path_edit.text().strip()
        root = Path(text or ".")
        if row:
            sample = self._format().map_relpath(
                row["rel_path"], self.src_lang, self.tgt_lang)
            self.preview.setText(fill(translate(
                "Export", "Files are written for the game, for example:\n%1"),
                root / sample))
        else:
            self.preview.setText(fill(translate(
                "Export", "Files of the language «%1» are written for the game"),
                self.tgt_lang))
        same = bool(text) and self.ru_root is not None and Path(text) == self.ru_root
        self.warning.setText(
            translate("Export",
                      "This is the folder the translation was imported from: "
                      "its files will be overwritten with the project content.")
            if same else "")
        self.warning.setVisible(same)

    def _existing_targets(self, root: Path) -> list[str]:
        """Which of the files we are about to write already exist there.

        We check exactly the paths we intend to write — dozens of them — instead
        of walking the tree: the destination is often a mod in Documents or the
        game folder itself, and an rglob over those hung the window for seconds,
        or for minutes on a half-typed path like «C:\\».
        """
        map_relpath = self._format().map_relpath
        rows = self.conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0",
            (self.project_id,)).fetchall()
        return [rel for rel in
                (map_relpath(r["rel_path"], self.src_lang, self.tgt_lang) for r in rows)
                if (root / rel).is_file()]

    def _format(self):
        """The localisation format of the project: the file names follow from it."""
        from pdxloc.core import loc_formats
        from pdxloc.project import get_loc_format

        return loc_formats.get(get_loc_format(self.conn) or loc_formats.DEFAULT)

    def _run(self) -> None:
        prefs.set("export/include_machine", self.machine_check.isChecked())
        options = ExportOptions(
            mode="translated_only" if self.radio_translated.isChecked() else "all_fallback_en",
            include_stale=self.stale_check.isChecked(),
            include_machine=self.machine_check.isChecked(),
        )
        text = self.path_edit.text().strip()
        if not text:
            QMessageBox.warning(
                self, translate("Export", "Writing the translation"),
                translate("Export", "Enter the mod folder."))
            return
        out_root = Path(text)
        existing = self._existing_targets(out_root)
        if existing:
            backup = (translate("Export",
                                "Previous versions will be kept in the backups "
                                "folder.")
                      if self.backup_check.isChecked()
                      else translate("Export",
                                     "Backup is off — there will be nothing to "
                                     "restore the previous versions from."))
            answer = QMessageBox.question(
                self, translate("Export", "Writing the translation"),
                fill(translate(
                    "Export",
                    "The folder already holds %1 translation files — they will "
                    "be overwritten with the project content.\n\nThe project is "
                    "the source of truth: rows it does not have will disappear "
                    "from the files.\n%2\n\nContinue?"), len(existing), backup))
            if answer != QMessageBox.Yes:
                return
        self.buttons.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = export_project(self.conn, self.project_id, options,
                                    out_root=out_root,
                                    backup=self.backup_check.isChecked())
        except OSError as e:
            QMessageBox.critical(
                self, translate("Export", "Writing the translation"),
                fill(translate("Export", "Write error:\n%1"), e))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.buttons.setEnabled(True)

        project_mod.set_export_root(self.conn, out_root)
        if self.ru_root is None:
            # The project had no translation folder — this write is what creates
            # one. Remembering it here is what lets the next scan read those files
            # back and notice an edit made outside the application.
            project_mod.set_translation_root(self.conn, out_root, self.project_id)
            self.ru_root = out_root
        project_mod.set_last_export_at(self.conn)
        lines = [
            fill(translate("Export", "Files written: %1"), report.files_written),
            fill(translate("Export", "Files unchanged: %1"), report.files_unchanged),
            fill(translate("Export", "Rows written: %1"), report.keys_written),
            fill(translate("Export", "Skipped (no translation): %1"),
                 report.keys_skipped),
        ]
        if report.keys_fallback_en:
            lines.append(fill(translate("Export", "Left in English: %1"),
                              report.keys_fallback_en))
        if report.backup_dir:
            lines.append(fill(translate("Export", "Previous versions: %1"),
                              report.backup_dir))
        lines.append("")
        rows_word = translate("Export", "rows")
        for rel, w, s in report.per_file:
            skipped = (fill(translate("Export", " (skipped %1)"), s) if s else "")
            lines.append(f"  {rel}: {w} {rows_word}{skipped}")
        self.report_box.setPlainText("\n".join(lines))
        self.report_box.show()
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)

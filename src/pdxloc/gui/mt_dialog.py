"""Пакетный машинный перевод: охват, предполётная оценка, прогон, сводка.

Операция трогает тысячи строк, стоит денег и ходит в сеть, поэтому устроена как
загрузка перевода из мода: сперва видно, **сколько именно строк** и во что это
обойдётся, и только потом кнопка. Записанное уходит одной пачкой и снимается
одним Ctrl+Z — об этом сказано прямо в подтверждении, а не только в справке.

Денежной оценки здесь нет намеренно. Таблица цен, зашитая в редко пересобираемый
exe, устареет за месяцы, а неверная цифра про деньги хуже отсутствующей.
Показываем то, что знаем точно: строки, символы, запросы и примерное время.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from pdxloc import project
from pdxloc.core import mt, mt_run, unit_ops
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.statuses import Status
from pdxloc.core.unit_ops import has_nothing_to_translate
from pdxloc.gui import mt_worker, prefs
from pdxloc.gui.widgets import HintLabel, WarningLabel

# Охваты: значение -> (подпись, статусы). Порядок — как в списке.
SCOPES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("selected", QT_TRANSLATE_NOOP("MtDialog", "Selected rows"), ()),
    ("untranslated", QT_TRANSLATE_NOOP("MtDialog", "Not translated"),
     (Status.UNTRANSLATED.value,)),
    ("untranslated_auto",
     QT_TRANSLATE_NOOP("MtDialog", "Not translated and filled from memory"),
     (Status.UNTRANSLATED.value, Status.AUTO.value)),
    ("all", QT_TRANSLATE_NOOP("MtDialog", "The whole project"), ()),
)

# Выше этого порога спрашиваем подтверждение: прогон уже долгий и заметный.
CONFIRM_ROWS = 500
CONFIRM_CHARS = 100_000

# Грубая оценка ответа сервиса. Точность здесь не нужна — нужен порядок величины,
# чтобы человек понимал, уходить ему пить чай или ждать.
_LATENCY_GUESS_SEC = 1.5


def collect_rows(
    conn: sqlite3.Connection,
    project_id: int,
    scope: str,
    *,
    selected_ids: list[int] | None = None,
    include_stale: bool = False,
) -> list[mt_run.MtRow]:
    """Строки, которые пойдут в перевод.

    Исключения одинаковы для всех охватов и не обсуждаются:

    * удалённые — их нет в оригинале;
    * «Игнорируется», «Проверено», «Кастомный» — там уже принято решение;
    * строки из одной разметки — отправлять голый `[GetName]` в платный сервис
      значит платить за ничто;
    * «Устарело» — только по отдельной галке: в них вложен труд человека, и
      затирать его молча нельзя.
    """
    wanted = next((group for name, _, group in SCOPES if name == scope), ())
    query = ["SELECT u.id, u.key, u.en_text FROM units u",
             "JOIN files f ON f.id = u.file_id",
             "WHERE f.project_id = ? AND u.is_deleted = 0",
             "AND u.en_text IS NOT NULL"]
    params: list = [project_id]

    if scope == "selected":
        ids = [i for i in (selected_ids or []) if i is not None]
        if not ids:
            return []
        query.append(f"AND u.id IN ({','.join('?' * len(ids))})")
        params.extend(ids)
    elif wanted:
        query.append(f"AND u.status IN ({','.join('?' * len(wanted))})")
        params.extend(wanted)

    # Что не переводим никогда — вне зависимости от охвата.
    never = [Status.IGNORED.value, Status.REVIEWED.value, Status.CUSTOM.value]
    if not include_stale:
        never.append(Status.STALE.value)
    query.append(f"AND u.status NOT IN ({','.join('?' * len(never))})")
    params.extend(never)

    rows = conn.execute(" ".join(query), params).fetchall()
    return [mt_run.MtRow(unit_id=r["id"], key=r["key"], text=r["en_text"])
            for r in rows
            if not has_nothing_to_translate(r["en_text"])]


class MtDialog(QDialog):
    """Окно пакетного перевода."""

    translated = Signal()      # строки изменились — обновить таблицу и счётчики
    showUnitRequested = Signal(int)

    def __init__(self, conn: sqlite3.Connection, project_id: int,
                 project_path, selected_ids=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.project_path = project_path
        self.selected_ids = list(selected_ids or [])
        self.report: mt_run.MtReport | None = None
        self._thread = None
        self._worker = None

        self.setWindowTitle(translate("MtDialog", "Machine translation"))
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._run_tab(), translate("MtDialog", "Translate"))
        self.tabs.addTab(self._manual_tab(),
                         translate("MtDialog", "Through a web translator"))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.start_button = self.buttons.button(QDialogButtonBox.Ok)
        self.start_button.setText(translate("MtDialog", "Translate"))
        self.buttons.accepted.connect(self._start)
        self.buttons.rejected.connect(self.reject)
        self.interrupt = QPushButton(translate("MtDialog", "Interrupt"))
        self.buttons.addButton(self.interrupt, QDialogButtonBox.ActionRole)
        self.interrupt.clicked.connect(self._on_interrupt)
        self.interrupt.hide()          # добавлять надо до скрытия, иначе не встанет
        layout.addWidget(self.buttons)

        self._refresh_estimate()

    # --- вкладка прогона ---

    def _run_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)

        provider_name = prefs.get("mt/provider")
        label = mt.provider_labels().get(provider_name, provider_name)
        self.service = QLabel(fill(
            translate("MtDialog", "Service: %1"), translate("Mt", label)))
        box.addWidget(self.service)
        if provider_name == "none":
            box.addWidget(WarningLabel(translate(
                "MtDialog", "No service is set up — choose one in "
                            "«File → Preferences → Machine translation»")))

        box.addWidget(QLabel(translate("MtDialog", "Which rows to translate:")))
        self.scope_group = QButtonGroup(self)
        self.scope_buttons: dict[str, QRadioButton] = {}
        for name, caption, _ in SCOPES:
            button = QRadioButton(translate("MtDialog", caption))
            self.scope_group.addButton(button)
            self.scope_buttons[name] = button
            box.addWidget(button)
        self.scope_buttons["selected"].setEnabled(bool(self.selected_ids))
        default = "selected" if self.selected_ids else "untranslated"
        self.scope_buttons[default].setChecked(True)

        self.include_stale = QCheckBox(translate(
            "MtDialog", "Also re-translate outdated rows (their existing "
                        "translation will be replaced)"))
        box.addWidget(self.include_stale)

        # Подписываемся, только когда все органы собраны: `setChecked` выше уже
        # шлёт `toggled`, а пересчёт охвата читает и галку «устаревшие».
        for button in self.scope_buttons.values():
            button.toggled.connect(self._refresh_estimate)
        self.include_stale.toggled.connect(self._refresh_estimate)
        box.addWidget(HintLabel(translate(
            "MtDialog",
            "Reviewed, custom and ignored rows are never touched, nor are rows "
            "with nothing to translate — a bare [GetName] costs money and "
            "returns nothing.")))

        self.estimate = QLabel()
        self.estimate.setWordWrap(True)
        box.addWidget(self.estimate)

        self.progress = QProgressBar()
        self.progress.hide()
        box.addWidget(self.progress)
        self.status = QLabel()
        box.addWidget(self.status)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.linkActivated.connect(self._on_summary_link)
        box.addWidget(self.summary)
        box.addStretch(1)
        return page

    # --- ручной веб-режим ---

    def _manual_tab(self) -> QWidget:
        """Перевод через браузер: ключей не нужно, работает с чем угодно.

        Единственный режим, доступный тому, у кого нет ни одной подписки, — и
        потому он полноправная вкладка, а не запасной выход.
        """
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)

        box.addWidget(HintLabel(translate(
            "MtDialog",
            "Rows are taken by the same rules as on the «Translate» tab, and "
            "the result is written the same way — the only difference is that "
            "you carry the text to a translator yourself.")))

        self.manual_counter = QLabel()
        box.addWidget(self.manual_counter)

        box.addWidget(QLabel(translate(
            "MtDialog", "Copy this into a web translator of your choice:")))
        self.manual_out = QPlainTextEdit()
        self.manual_out.setReadOnly(True)
        box.addWidget(self.manual_out, 1)
        copy = QPushButton(translate("MtDialog", "Copy"))
        copy.clicked.connect(self._manual_copy)
        box.addWidget(copy)

        box.addWidget(QLabel(translate("MtDialog", "Paste the result here:")))
        self.manual_in = QPlainTextEdit()
        box.addWidget(self.manual_in, 1)

        self.manual_apply = QPushButton(translate(
            "MtDialog", "Take the result and go to the next batch"))
        self.manual_apply.clicked.connect(self._manual_apply)
        box.addWidget(self.manual_apply)

        self.manual_note = WarningLabel("")
        self.manual_note.setWordWrap(True)
        box.addWidget(self.manual_note)
        return page

    def _on_tab_changed(self, index: int) -> None:
        # Кнопка «Перевести» относится к первой вкладке; на второй ей нечего делать
        manual = index == 1
        self.start_button.setVisible(not manual)
        if manual:
            self._manual_reset()

    def _manual_reset(self) -> None:
        """Пересобрать очередь пачек по текущему охвату."""
        self._manual_rows = self.rows_for_run()
        budget = prefs.get("mt/char_budget")
        batches, _oversized = mt_run.plan_batches(
            [r.text for r in self._manual_rows], budget)
        self._manual_batches = batches
        self._manual_index = 0
        self._manual_batch_id = None
        self._manual_show()

    def _manual_show(self) -> None:
        self.manual_in.clear()
        self.manual_note.clear()
        if self._manual_index >= len(self._manual_batches):
            self.manual_out.clear()
            self.manual_counter.setText(translate(
                "MtDialog", "Nothing left to translate."))
            self.manual_apply.setEnabled(False)
            return

        from pdxloc.core.mt_providers import manual as manual_mode

        batch = self._manual_batches[self._manual_index]
        kind = (mt.ASCII_TOKENS if prefs.get("mt/manual_ascii_tokens")
                else mt.UNICODE_TOKENS)
        self._manual_mappings = []
        shielded = []
        for i in batch:
            text, mapping = mt.shield_tags(self._manual_rows[i].text, kind)
            shielded.append(text)
            self._manual_mappings.append(mapping)
        self.manual_out.setPlainText(manual_mode.join(
            shielded, prefs.get("mt/manual_separator")))
        self.manual_counter.setText(fill(
            translate("MtDialog", "Batch %1 of %2 · %3 rows"),
            self._manual_index + 1, len(self._manual_batches), len(batch)))
        self.manual_apply.setEnabled(True)

    def _manual_copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.manual_out.toPlainText())

    def _manual_apply(self) -> None:
        """Разобрать вставленное и записать. Расхождение — не применяем ничего."""
        from pdxloc.core.mt_errors import MtResponseError
        from pdxloc.core.mt_providers import manual as manual_mode

        batch = self._manual_batches[self._manual_index]
        try:
            parts = manual_mode.split(
                self.manual_in.toPlainText(), len(batch),
                prefs.get("mt/manual_separator"))
        except MtResponseError as error:
            self.manual_note.setText(error.message)
            return

        if self._manual_batch_id is None:
            self._manual_batch_id = unit_ops.new_batch_id()
        written = 0
        for position, (index, raw) in enumerate(zip(batch, parts, strict=True)):
            mapping = self._manual_mappings[position]
            text = mt.unshield(raw, mapping)
            if unit_ops.save_machine_text(
                    self.conn, self._manual_rows[index].unit_id, text,
                    batch_id=self._manual_batch_id):
                written += 1
        self.translated.emit()

        self._manual_index += 1
        self._manual_show()
        if written:
            self.manual_note.clear()

    # --- предполётная оценка ---

    def current_scope(self) -> str:
        for name, button in self.scope_buttons.items():
            if button.isChecked():
                return name
        return "untranslated"

    def rows_for_run(self) -> list[mt_run.MtRow]:
        return collect_rows(
            self.conn, self.project_id, self.current_scope(),
            selected_ids=self.selected_ids,
            include_stale=self.include_stale.isChecked())

    def _refresh_estimate(self) -> None:
        rows = self.rows_for_run()
        chars = sum(len(r.text) for r in rows)
        budget = prefs.get("mt/char_budget")
        batches, oversized = mt_run.plan_batches([r.text for r in rows], budget)
        seconds = len(batches) * (_LATENCY_GUESS_SEC
                                  + prefs.get("mt/throttle_ms") / 1000.0)
        self.estimate.setText(fill(
            translate("MtDialog",
                      "Rows: %1 · characters: %2 · requests: %3 · roughly %4 "
                      "minutes"),
            len(rows), chars, len(batches), max(1, round(seconds / 60))))
        self.start_button.setEnabled(
            bool(rows) and prefs.get("mt/provider") != "none")
        if oversized:
            self.status.setText(fill(translate(
                "MtDialog", "%1 rows are longer than the service takes in one "
                            "request and will be left untouched"), len(oversized)))
        else:
            self.status.clear()

    # --- прогон ---

    def _start(self) -> None:
        rows = self.rows_for_run()
        if not rows:
            return
        chars = sum(len(r.text) for r in rows)
        if len(rows) >= CONFIRM_ROWS or chars >= CONFIRM_CHARS:
            answer = QMessageBox.question(
                self, translate("MtDialog", "Machine translation"),
                fill(translate(
                    "MtDialog",
                    "Send %1 rows (%2 characters) to the service?\n\n"
                    "The result is written with the «Machine (unchecked)» "
                    "status. The whole run is one batch — Ctrl+Z undoes it "
                    "all."), len(rows), chars))
            if answer != QMessageBox.Yes:
                return

        provider_name = prefs.get("mt/provider")
        self.batch_id = unit_ops.new_batch_id()
        langs = project.languages(self.conn, self.project_id)

        self._worker = mt_worker.MtWorker(
            self.project_path, rows, provider_name,
            mt_worker.config_from_prefs(provider_name),
            langs.src_locale, langs.tgt_locale, self.batch_id,
            budget=prefs.get("mt/char_budget"),
            throttle_ms=prefs.get("mt/throttle_ms"),
            retries=prefs.get("mt/retries"))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread = mt_worker.start(self._worker, self)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)

        self._set_running(True)
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        self.start_button.setVisible(not running)
        self.interrupt.setVisible(running)
        self.progress.setVisible(running)
        for button in self.scope_buttons.values():
            button.setEnabled(not running and
                              (button is not self.scope_buttons["selected"]
                               or bool(self.selected_ids)))
        self.include_stale.setEnabled(not running)

    def _on_progress(self, done: int, total: int, key: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status.setText(fill(
            translate("MtDialog", "Translated %1 of %2"), done, total))

    def _on_interrupt(self) -> None:
        self.interrupt.setEnabled(False)
        self.status.setText(translate("MtDialog", "Interrupting…"))
        if self._worker is not None:
            self._worker.cancel()

    def _on_finished(self, report) -> None:
        self.report = report
        self._set_running(False)
        self.interrupt.setEnabled(True)
        self.status.clear()
        # Соединение диалога не участвовало в записи — перечитываем счётчики
        self.translated.emit()
        self.summary.setText(self._summary_html(report))
        self._refresh_estimate()

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self.interrupt.setEnabled(True)
        self.status.clear()
        QMessageBox.critical(self, translate("MtDialog", "Machine translation"),
                             message)

    # --- сводка ---

    def _summary_html(self, report) -> str:
        lines = [report.summary().replace("\n", "<br>")]
        broken = report.placeholders_lost + [
            (uid, key, None) for uid, key, _ in report.failures]
        if broken:
            lines.append("<br>" + translate(
                "MtDialog", "Rows worth looking at:"))
            for unit_id, key, _ in broken[:20]:
                lines.append(f'<a href="{unit_id}">{key}</a>')
            if len(broken) > 20:
                lines.append(fill(translate("MtDialog", "… and %1 more"),
                                  len(broken) - 20))
        return "<br>".join(lines)

    def _on_summary_link(self, href: str) -> None:
        try:
            unit_id = int(href)
        except ValueError:
            return
        self.showUnitRequested.emit(unit_id)

    # --- закрытие ---

    def closeEvent(self, event) -> None:
        """Пока идёт прогон, окно не закрываем — сперва прерывание."""
        if self._thread is not None and self._thread.isRunning():
            self._on_interrupt()
            event.ignore()
            return
        super().closeEvent(event)

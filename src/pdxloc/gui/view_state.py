"""Единственный источник правды о том, что и в каком порядке показано.

Фильтр ставится из пяти мест: панель фильтров над таблицей, чипы статус-бара,
дерево файлов, сводка сканирования и меню «Фильтры». Раньше каждое из них
держало собственное состояние — чипы, например, подсвечивались только когда
кликнули по самим чипам, а кнопка «Показать» в сводке двигала комбобокс мимо
них. Теперь состояние здесь одно, а органы управления — только его витрины:
пишут сюда и перерисовываются по сигналу.

Сигналов два, и это существенно:

* `changed` — сменился состав строк, нужен новый SQL-запрос и пересчёт
  замечаний (по 5к строк это порядка 45 мс);
* `sortChanged` — сменился только порядок, хватит перестановки уже загруженных
  строк (5–10 мс).

Гнать клик по заголовку колонки через полную перезагрузку значило бы
пересчитывать все проверки качества на каждое нажатие.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pdxloc.gui.sorting import FIRST, SECOND, SortState
from pdxloc.gui.units_model import COL_ISSUES, UnitFilters


class ViewState(QObject):
    changed = Signal()       # состав строк изменился
    sortChanged = Signal()   # изменился только порядок

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status: str | None = None
        self.search = ""
        self.show_deleted = False
        self.file_rel: str | None = None
        self.file_prefix: str | None = None
        self.sort = SortState()

    # --- производное ---

    @property
    def only_issues(self) -> bool:
        """Фильтр «только с замечаниями» — второй шаг колонки «!».

        Отдельного поля нет намеренно: пока их было два (чекбокс и колонка),
        они бы разъезжались. Чекбокс, пункт меню и кнопка панели — три окна в
        одно значение.
        """
        return self.sort.column == COL_ISSUES and self.sort.step == SECOND

    @property
    def sort_spec(self) -> tuple[int, bool] | None:
        """(колонка, по убыванию) либо None — естественный порядок."""
        if self.sort.column is None:
            return None
        # у колонки «!» второй шаг сужает выборку, а не переворачивает порядок:
        # показывать проблемные снизу незачем
        descending = self.sort.step == SECOND and self.sort.column != COL_ISSUES
        return self.sort.column, descending

    def filters(self) -> UnitFilters:
        return UnitFilters(
            status=self.status,
            file_rel=self.file_rel,
            file_prefix=self.file_prefix,
            search=self.search,
            show_deleted=self.show_deleted,
            only_issues=self.only_issues,
        )

    # --- изменение ---

    def set_status(self, value: str | None) -> None:
        if value != self.status:
            self.status = value
            self.changed.emit()

    def set_search(self, value: str) -> None:
        value = value.strip()
        if value != self.search:
            self.search = value
            self.changed.emit()

    def set_show_deleted(self, value: bool) -> None:
        if value != self.show_deleted:
            self.show_deleted = value
            self.changed.emit()

    def set_only_issues(self, value: bool) -> None:
        if value == self.only_issues:
            return
        if value:
            self.sort.set(COL_ISSUES, SECOND)
        else:
            # Галку сняли — фильтр уходит, но порядок «проблемные сверху»
            # остаётся: строки не прыгают, когда выборка расширяется, и видно,
            # где проблемные лежат относительно остальных.
            self.sort.step = FIRST
        self.changed.emit()

    def set_file(self, file_rel: str | None, file_prefix: str | None) -> None:
        if (file_rel, file_prefix) != (self.file_rel, self.file_prefix):
            self.file_rel, self.file_prefix = file_rel, file_prefix
            self.changed.emit()

    def click_column(self, column: int) -> None:
        was_filtered = self.only_issues
        self.sort.click(column)
        # состав строк меняет только колонка «!»; остальным хватит перестановки
        if was_filtered != self.only_issues:
            self.changed.emit()
        else:
            self.sortChanged.emit()

    def set_sort(self, column: int | None, descending: bool = False) -> None:
        """Задать сортировку явно — из подменю «Вид → Сортировка»."""
        was_filtered = self.only_issues
        self.sort.set(column, SECOND if descending else FIRST)
        if was_filtered != self.only_issues:
            self.changed.emit()
        else:
            self.sortChanged.emit()

    def reset_filters(self) -> None:
        """Снять фильтры, но не сортировку.

        Порядок строк ничего не прячет, а `jump_to_unit` зовёт сброс именно
        затем, чтобы показать строку, спрятанную фильтром.
        """
        self.status = None
        self.search = ""
        self.show_deleted = False
        self.file_rel = self.file_prefix = None
        if self.only_issues:
            self.sort.step = FIRST      # фильтр снят, порядок сохранён
        self.changed.emit()

"""Панель-дерево файлов проекта со счётчиками перевода (как левая панель EET)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from pdxloc.core.i18n import translate
from pdxloc.core.stats import FileStats
from pdxloc.gui import theme

CTX = "FileTree"

_ROLE_FILE = Qt.UserRole          # rel_path файла (None у папок)
_ROLE_PREFIX = Qt.UserRole + 1    # префикс папки (None у файлов)


class FileTreePanel(QWidget):
    # (file_rel | None, file_prefix | None); (None, None) = все
    filterSelected = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.tree)
        self._file_items: dict[str, QTreeWidgetItem] = {}
        self._dir_items: dict[str, QTreeWidgetItem] = {}
        self._root: QTreeWidgetItem | None = None
        self._silent = False
        # последние счётчики: цвета подписей зависят от темы, а пересчитывать
        # их из базы ради перекраски незачем — соединение к тому же может быть
        # уже закрыто (проект закрыли, а тему переключили)
        self._stats: list[FileStats] = []
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        if self._file_items or self._root is not None:
            self.update_counts(self._stats)

    def retranslate(self) -> None:
        """Единственная переводимая подпись дерева — корневой «ВСЕ»."""
        if self._root is not None:
            self.update_counts(self._stats)

    # --- построение ---

    def populate(self, stats: list[FileStats]) -> None:
        self._silent = True
        self.tree.clear()
        self._file_items.clear()
        self._dir_items.clear()

        self._root = QTreeWidgetItem([translate("FileTree", "ALL")])
        self._root.setData(0, _ROLE_FILE, None)
        self._root.setData(0, _ROLE_PREFIX, None)
        font = QFont()
        font.setBold(True)
        self._root.setFont(0, font)
        self.tree.addTopLevelItem(self._root)

        for fs in stats:
            parent = self._root
            parts = fs.rel_path.split("/")
            for depth in range(len(parts) - 1):
                prefix = "/".join(parts[: depth + 1])
                if prefix not in self._dir_items:
                    item = QTreeWidgetItem([parts[depth]])
                    item.setData(0, _ROLE_FILE, None)
                    item.setData(0, _ROLE_PREFIX, prefix)
                    parent.addChild(item)
                    self._dir_items[prefix] = item
                parent = self._dir_items[prefix]
            item = QTreeWidgetItem([parts[-1]])
            item.setData(0, _ROLE_FILE, fs.rel_path)
            item.setData(0, _ROLE_PREFIX, None)
            parent.addChild(item)
            self._file_items[fs.rel_path] = item

        self.update_counts(stats)
        self.tree.expandAll()
        self._silent = False

    def update_counts(self, stats: list[FileStats]) -> None:
        """Обновить счётчики без пересборки дерева."""
        self._stats = stats
        total_all = done_all = 0
        by_path = {fs.rel_path: fs for fs in stats}
        for rel_path, item in self._file_items.items():
            fs = by_path.get(rel_path)
            if fs is None:
                continue
            total_all += fs.total
            done_all += fs.done
            name = rel_path.rsplit("/", 1)[-1]
            self._set_label(item, name, fs.done, fs.total)
        # папки — суммой по детям
        for prefix, item in self._dir_items.items():
            done = total = 0
            for fs in stats:
                if fs.rel_path.startswith(prefix + "/"):
                    done += fs.done
                    total += fs.total
            self._set_label(item, prefix.rsplit("/", 1)[-1], done, total)
        if self._root is not None:
            self._set_label(self._root, translate("FileTree", "ALL"), done_all, total_all)

    @staticmethod
    def _set_label(item: QTreeWidgetItem, name: str, done: int, total: int) -> None:
        item.setText(0, f"{name}  {done}/{total}")
        complete = total > 0 and done == total
        item.setForeground(0, QBrush(theme.qcolor(
            "tree.complete" if complete else "tree.partial")))
        font = item.font(0)
        font.setBold(complete or (item.data(0, _ROLE_FILE) is None and item.data(0, _ROLE_PREFIX) is None))
        item.setFont(0, font)

    # --- выбор ---

    def _on_selection(self) -> None:
        if self._silent:
            return
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        self.filterSelected.emit(item.data(0, _ROLE_FILE), item.data(0, _ROLE_PREFIX))

    def clear_selection(self) -> None:
        self._silent = True
        self.tree.clearSelection()
        if self._root is not None:
            self._root.setSelected(True)
        self._silent = False

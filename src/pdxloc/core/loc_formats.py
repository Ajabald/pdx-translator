"""Форматы локализации Paradox: какой парсер применить к этим файлам.

У серии их два, и делит их не игра, а поколение движка:

| | `yml` | `csv` |
|---|---|---|
| игры | CK3, HOI4, EU4, Stellaris, Victoria 3, Imperator, EU5 | CK2, EU3, Victoria 2, HoI3 |
| файл | `mod_events_l_russian.yml` | `events.csv` |
| язык | папка и метка в имени файла | **колонка внутри строки** |
| кодировка | UTF-8 с BOM | cp1251 / cp1252 |

**Формат определяется по данным, а не по названию игры.** Так и задумано:
список игр в `core/games.py` открытый (своя игра заводится свободным именем), и
угадывать по имени пришлось бы каждый раз заново. А посмотреть в папку —
надёжно: `l_english:` в первой строке `.yml` ни с чем не спутать, как и
`#CODE;` в шапке `.csv`.

Ответ запоминается в файле проекта (`project_meta.loc_format`) — не ради
скорости, а ради определённости: дерево оригинала может уехать вместе с диском,
и тогда экспорт должен писать в том же формате, в каком читал, а не в том,
который угадается по остаткам.

Реализации живут в `core/paradox_yaml.py` и `core/paradox_csv.py`; здесь только
таблица «кто что умеет» и выбор.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from pdxloc.core import paradox_csv, paradox_yaml
from pdxloc.core.models import LocEntry, LocFile

YML = "yml"
CSV = "csv"


@dataclass(frozen=True, slots=True)
class LocFormat:
    """Формат и модуль, который его читает и пишет.

    Держим **модуль**, а не восемь ссылок на его функции: так подмена функции в
    тестах доходит до вызывающих (ссылка, снятая при импорте, о `monkeypatch`
    не узнает), и так очевидно, где искать реализацию.
    """

    id: str
    ext: str
    impl: ModuleType
    # нужна ли языку отдельная папка: у `csv` язык — колонка, и файл перевода
    # зовётся так же, как файл оригинала; деревья различаются только местом
    language_in_path: bool
    encodings: tuple[str, ...]

    # --- разбор и запись ---

    def parse_file(self, path: Path, *, language: str = "",
                   encoding: str = "") -> LocFile:
        return self.impl.parse_file(path, language=language, encoding=encoding)

    def render(self, language: str, entries: Iterable[LocEntry],
               trailing: str = "", **kwargs) -> str:
        return self.impl.render(language, entries, trailing, **kwargs)

    def write_file(self, path: Path, language: str, entries: Iterable[LocEntry],
                   trailing: str = "", **kwargs) -> None:
        self.impl.write_file(path, language, entries, trailing, **kwargs)

    def escape_value(self, text: str) -> str:
        return self.impl.escape_value(text)

    def unescape(self, text: str) -> str:
        return self.impl.unescape(text)

    # --- обход дерева ---

    def files(self, root: Path, language: str = "", *,
              skip_updated: bool = False) -> list[Path]:
        return self.impl.files(root, language, skip_updated=skip_updated)

    def map_relpath(self, rel_posix: str, from_lang: str, to_lang: str) -> str:
        return self.impl.map_relpath(rel_posix, from_lang, to_lang)

    def detect(self, root: Path) -> bool:
        return self.impl.detect(root)


FORMATS: dict[str, LocFormat] = {f.id: f for f in (
    LocFormat(id=YML, ext=".yml", impl=paradox_yaml,
              language_in_path=True, encodings=("utf-8-sig",)),
    LocFormat(id=CSV, ext=".csv", impl=paradox_csv,
              language_in_path=False, encodings=paradox_csv.ENCODINGS),
)}

# Порядок опроса: сперва нынешний формат серии. Он и встречается чаще, и
# опознаётся строже — у `csv` признак записи слабее (ключ, разделитель и
# что-то после), и таблицу данных от локализации отличает только содержимое.
ORDER: tuple[str, ...] = (YML, CSV)

DEFAULT = YML


def get(format_id: str) -> LocFormat:
    """Формат по идентификатору. Незнакомый — нынешний формат серии.

    Незнакомый не ошибка: значение приезжает из файла проекта, который мог быть
    заведён версией приложения, знавшей больше форматов.
    """
    return FORMATS.get(format_id, FORMATS[DEFAULT])


def detect(root: Path, *, default: str = DEFAULT) -> str:
    """Формат дерева по его содержимому. Пустая папка — формат по умолчанию."""
    if not root.is_dir():
        return default
    for format_id in ORDER:
        if FORMATS[format_id].detect(root):
            return format_id
    return default


def entries_of(loc_file: LocFile) -> Iterable[LocEntry]:
    """Записи файла — чтобы вызывающему не знать про поля модели."""
    return loc_file.entries


def normalize_newlines(text: str) -> str:
    """Перенос строки в виде, общем для обоих форматов, — для записи в базу.

    Настоящий перенос ломает и `.yml`, и `.csv` одинаково: запись разрывается
    пополам. Поэтому его приводим к двум символам сразу при сохранении, а не
    при выгрузке, — иначе база и файл расходятся ровно на этот символ, и
    следующее сканирование докладывает о правке, которой никто не делал.

    Остальное экранирование форматам не общее (в `.csv` ещё и точка с запятой —
    разделитель) и делается при записи файла, в `render`.
    """
    return paradox_yaml.escape_value(text)

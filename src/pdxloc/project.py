"""Файлы проектов (.pdxproj) и подключение баз памяти переводов.

Проект — самостоятельный файл SQLite: строки, файлы, память переводов, архив.
Его можно положить куда угодно и передать другому человеку.

Базы памяти переводов (.pdxtm) подключаются к соединению только на чтение;
поиск идёт по объединяющему представлению tm_all (см. attach_tm_sources).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pdxloc import db as db_module
from pdxloc import settings
from pdxloc.core import games
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.db import init_schema, register_functions

# Приоритет источников памяти переводов: свои переводы, затем экспорты чужих
# проектов, затем большие игровые базы.
KIND_PRIORITY = {"project-export": 1, "import": 2, "game": 3}
KIND_LABELS = {
    "game": QT_TRANSLATE_NOOP("Project", "game database"),
    "project-export": QT_TRANSLATE_NOOP("Project", "project export"),
    "import": QT_TRANSLATE_NOOP("Project", "import"),
}


def _uri(path: Path, mode: str) -> str:
    return f"file:{quote(str(path).replace(chr(92), '/'), safe='/:')}?mode={mode}"


# --- проекты ---

def create_project(
    path: Path,
    *,
    name: str,
    src_root: Path | str,
    tgt_root: Path | str,
    game: str = games.CK3,
    src_lang: str = "english",
    tgt_lang: str = "russian",
    src_locale: str = "",
    tgt_locale: str = "",
) -> sqlite3.Connection:
    """Создать новый файл проекта и вернуть открытое соединение.

    Локали по умолчанию пустые: это значит «совпадают с папкой языка», и
    заполнять их нужно только при переводе на язык, которого в игре нет.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(fill(translate(
            "Project", "The project file already exists: %1"), path))
    conn = open_project(path)
    conn.execute(
        "INSERT INTO projects (id, name, en_root, ru_root, game, src_lang, "
        "tgt_lang, src_locale, tgt_locale) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, str(src_root), str(tgt_root), game, src_lang, tgt_lang,
         src_locale, tgt_locale),
    )
    conn.commit()
    return conn


def open_project(path: Path, tm_paths: list[Path] | None = None) -> sqlite3.Connection:
    """Открыть файл проекта, применить схему и подключить базы памяти."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # uri=True нужен не только здесь: без него нельзя подключать базы по URI
    conn = sqlite3.connect(_uri(path, "rwc"), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    # Потолок журнала. Сканирование пишет весь проект одной транзакцией, и
    # `-wal` вырастал до размера самой базы (замер на ванильной HOI4: файл
    # 181 МБ, журнал 182 МБ) — а лежал он там до следующей записи, и каждое
    # открытие проекта начиналось с чтения этих мегабайт. После чекпоинта
    # файл теперь усекается сам.
    conn.execute("PRAGMA journal_size_limit = 67108864")
    register_functions(conn)
    init_schema(conn)
    conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('format', 'pdxproj')")
    conn.commit()
    attach_tm_sources(conn, tm_paths if tm_paths is not None else project_tm_paths(conn))
    return conn


def checkpoint(conn: sqlite3.Connection) -> None:
    """Перенести журнал в базу и усечь его.

    Зовётся там, где работа заведомо закончена: после сканирования, после
    импорта и при закрытии проекта. Сам по себе SQLite журнал не усекает — он
    накапливает страницы, и без этого рядом с проектом остаётся `-wal`
    размером с базу, который читается при каждом следующем открытии.

    Ошибка гасится намеренно: чекпоинт не может выполниться, пока базу читает
    кто-то ещё (открытое окно памяти переводов, фоновый счётчик), и это не
    повод мешать закрытию проекта — журнал доживёт до следующего раза.
    """
    try:
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass


def read_only_connection(path: Path) -> sqlite3.Connection:
    """Соединение только на чтение — для фоновых замеров.

    Не `open_project`: тот включает WAL, применяет схему и подключает базы
    памяти, а фоновому счётчику нужно лишь пересчитать строки, ничего не
    трогая в файле, который прямо сейчас открыт основным потоком.
    """
    conn = sqlite3.connect(_uri(Path(path), "ro"), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def project_companions(path: Path, *, with_backups: bool = False) -> list[Path]:
    """Файлы, из которых состоит проект на диске.

    Соединение открывается в режиме WAL (см. open_project), поэтому рядом с
    самим файлом живут `-wal` и `-shm`. Удалить только основной файл нельзя:
    следующий проект с тем же именем подхватит чужой журнал.
    """
    path = Path(path)
    files = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
    if with_backups:
        # копии перед миграциями схемы (db._backup_db_file) и база прежних версий
        files += sorted(path.parent.glob(f"{path.name}.v*.bak"))
        files += sorted(path.parent.glob(f"{path.name}.migrated"))
    return [f for f in files if f.exists()]


@dataclass(frozen=True)
class DeleteReport:
    """Что удалилось и как. `bypassed_trash` — то, что ушло мимо корзины."""

    removed: list[Path] = field(default_factory=list)
    bypassed_trash: list[Path] = field(default_factory=list)

    def __len__(self) -> int:       # вызывающие считают файлы, а не разбирают отчёт
        return len(self.removed)


def delete_project_file(path: Path, *, with_backups: bool = False) -> DeleteReport:
    """Удалить файл проекта вместе со спутниками.

    Уходит в корзину, если система умеет (см. core/trash). Занятый файл
    поднимает OSError — вызывающий обязан объяснить это пользователем, потому
    что причина почти всегда одна: проект ещё открыт.

    **Корзина срабатывает не всегда**, и это надо передать наверх: Windows не
    кладёт туда файл, который не помещается в её квоту, а проект перевода — это
    сотни мегабайт. Диалог перед удалением обещает корзину, поэтому случай
    «обещали, но удалили насмерть» обязан дойти до человека, а не потеряться
    здесь. Отсюда `bypassed_trash` вместо голого списка путей.
    """
    from pdxloc.core import trash

    report = DeleteReport()
    for target in project_companions(path, with_backups=with_backups):
        outcome = trash.remove(target)
        if outcome == "missing":
            continue
        report.removed.append(target)
        if outcome == "unlink" and trash.available():
            report.bypassed_trash.append(target)
    return report


@dataclass(frozen=True)
class ProjectLanguages:
    """Языки проекта: папка игры отдельно, язык текста отдельно.

    `src_lang`/`tgt_lang` определяют имена папок, метку `_l_xxx` в имени файла
    и заголовок `l_xxx:` — это диктует игра. `src_locale`/`tgt_locale` говорят,
    на каком языке текст: по ним работают машинный перевод, именование баз
    памяти и языковые правила проверки. Совпадают они почти всегда, но не
    когда переводят на язык, которого в игре нет.
    """

    src_lang: str
    tgt_lang: str
    src_locale: str
    tgt_locale: str

    @property
    def split(self) -> bool:
        """Расходятся ли папка и язык текста — есть ли о чём говорить в UI."""
        from pdxloc.core import languages

        return (self.src_locale != languages.default_locale(self.src_lang)
                or self.tgt_locale != languages.default_locale(self.tgt_lang))


def languages(conn: sqlite3.Connection, project_id: int = 1) -> ProjectLanguages:
    """Языки проекта с подставленными локалями.

    Раньше это разбирал каждый потребитель сам — пятью копиями строки
    `proj["src_lang"] if "src_lang" in keys else "english"`, и добавление
    локалей означало бы шестую и седьмую.
    """
    from pdxloc.core import languages as lang_mod

    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    keys = row.keys() if row is not None else ()

    def value(name: str, fallback: str) -> str:
        return row[name] if name in keys and row[name] else fallback

    src_lang = value("src_lang", "english")
    tgt_lang = value("tgt_lang", "russian")
    return ProjectLanguages(
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        src_locale=lang_mod.resolve_locale(src_lang, value("src_locale", "")),
        tgt_locale=lang_mod.resolve_locale(tgt_lang, value("tgt_locale", "")),
    )


def set_languages(conn: sqlite3.Connection, langs: ProjectLanguages,
                  project_id: int = 1) -> None:
    """Записать языки проекта.

    Локаль, совпадающую с выведенной из папки, храним пустой: так проект не
    зарастает значениями, которые и так известны, а смена папки языка сама
    тянет за собой язык текста.
    """
    from pdxloc.core import languages as lang_mod

    def stored(language: str, locale: str) -> str:
        return "" if locale == lang_mod.default_locale(language) else locale

    conn.execute(
        "UPDATE projects SET src_lang = ?, tgt_lang = ?, "
        "src_locale = ?, tgt_locale = ? WHERE id = ?",
        (langs.src_lang, langs.tgt_lang,
         stored(langs.src_lang, langs.src_locale),
         stored(langs.tgt_lang, langs.tgt_locale), project_id))
    conn.commit()


def project_name(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT name FROM projects WHERE id = 1").fetchone()
    return row["name"] if row else translate("Project", "(unnamed)")


# --- игра проекта ---

def game(conn: sqlite3.Connection, project_id: int = 1) -> str:
    """Идентификатор игры. Пусто в базе — CK3: других игр приложение не знало."""
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None or "game" not in row.keys() or not row["game"]:
        return games.CK3
    return row["game"]


def set_game(conn: sqlite3.Connection, game_id: str, project_id: int = 1) -> None:
    conn.execute("UPDATE projects SET game = ? WHERE id = ?", (game_id, project_id))
    conn.commit()


def read_game(path: Path) -> str | None:
    """Игра проекта, не открывая его. `None` — файл не читается как проект.

    Соединением только на чтение и без применения схемы: спрашивают до
    открытия, чтобы успеть перенести файл в свой загон — открытый проект
    держит `-wal`, и переносить его было бы поздно.
    """
    try:
        conn = read_only_connection(path)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = 1").fetchone()
        if row is None:
            return None
        return row["game"] if "game" in row.keys() and row["game"] else games.CK3
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def move_project_file(path: Path, target_dir: Path) -> Path:
    """Перенести файл проекта со спутниками в другую папку.

    Спутники обязательны: `-wal` и `-shm` — часть проекта, и файл, уехавший без
    журнала, в лучшем случае потеряет незаписанное, а в худшем подхватит чужой
    журнал от одноимённого соседа.
    """
    path = Path(path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target == path:
        return path
    if target.exists():
        raise FileExistsError(fill(translate(
            "Project", "The file already exists: %1"), target))
    for companion in project_companions(path):
        companion.rename(target_dir / companion.name)
    return target


def save_project_as(conn: sqlite3.Connection, new_path: Path) -> Path:
    """Сохранить копию проекта по новому пути (соединение закрывается вызывающим)."""
    new_path = Path(new_path)
    if new_path.exists():
        raise FileExistsError(fill(translate(
            "Project", "The file already exists: %1"), new_path))
    new_path.parent.mkdir(parents=True, exist_ok=True)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # VACUUM INTO не работает внутри транзакции и требует отсутствия цели
    conn.execute("VACUUM INTO ?", (str(new_path),))
    return new_path


# --- перенос базы прежних версий ---

def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip(" .")
    return cleaned or "project"


# --- базы памяти переводов ---

def tm_meta(path: Path, *, with_count: bool = False) -> dict[str, str] | None:
    """Прочитать описание базы. None, если файл не является базой памяти.

    Число записей считается только по просьбе: `COUNT(*)` идёт полным сканом
    таблицы (у ванильной базы CK3 это 244 118 строк и 144 МБ файла), а
    спрашивают описание в основном затем, чтобы узнать «это вообще база
    памяти?» — при открытии проекта так делается на каждую подключённую базу.
    Показать число нужно ровно в двух местах, и оба зовут `list_tm_databases`.
    """
    try:
        conn = sqlite3.connect(_uri(Path(path), "ro"), uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = conn.execute("SELECT key, value FROM tm_meta").fetchall()
        meta = {k: v for k, v in rows}
        if meta.get("format") != "pdxtm":
            return None
        if with_count:
            meta["entries"] = str(
                conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0])
        return meta
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def list_tm_databases(directory: Path | None = None, *,
                      game: str | None = None) -> list[tuple[Path, dict[str, str]]]:
    """Базы памяти переводов в папке.

    `game` выбирает загон своей игры (`Bdd\\CK3`), и в него же попадает корень
    `Bdd`: базы, собранные до появления загонов, лежат там, и прятать их от
    человека значило бы объявить их пропавшими.
    """
    if directory is not None:
        directories = [Path(directory)]
    elif game is not None:
        directories = [settings.bdd_pen(game), settings.bdd_dir()]
    else:
        directories = [settings.bdd_dir()]

    result: list[tuple[Path, dict[str, str]]] = []
    seen: set[Path] = set()
    for folder in directories:
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob(f"*{settings.TM_EXT}")):
            if p in seen:
                continue
            meta = tm_meta(p, with_count=True)
            if meta is not None:
                seen.add(p)
                result.append((p, meta))
    return result


def any_tm_database() -> bool:
    """Есть ли на машине хоть одна база памяти.

    Отдельно от `all_tm_databases`, потому что вопрос задаётся при каждом
    открытии проекта, а ответ «да» виден по первому же файлу: собирать список
    с описанием и числом записей ради него значило бы прочитать все базы
    целиком — сотни мегабайт на ровном месте.
    """
    root = settings.bdd_dir()
    if not root.is_dir():
        return False
    folders = [root, *(p for p in root.glob("*") if p.is_dir())]
    return any(tm_meta(p) is not None
               for folder in folders
               for p in folder.glob(f"*{settings.TM_EXT}"))


def all_tm_databases() -> list[tuple[Path, dict[str, str]]]:
    """Базы всех игр разом — для вопроса «есть ли на машине хоть одна».

    Загоны обходятся на один уровень: глубже человек раскладывает по-своему, и
    угадывать его порядок не наше дело.
    """
    root = settings.bdd_dir()
    folders = [root, *sorted(p for p in root.glob("*") if p.is_dir())] \
        if root.is_dir() else []
    result: list[tuple[Path, dict[str, str]]] = []
    for folder in folders:
        result += list_tm_databases(folder)
    return result


def get_tm_sources(conn: sqlite3.Connection) -> list[str]:
    """Имена подключённых баз (без путей — проект остаётся переносимым)."""
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = 'tm_sources'").fetchone()
    if not row or not row["value"]:
        return []
    try:
        return [str(x) for x in json.loads(row["value"])]
    except (ValueError, TypeError):
        return []


def set_tm_sources(conn: sqlite3.Connection, names: list[str]) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES ('tm_sources', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(names, ensure_ascii=False),))
    conn.commit()


# --- папка вывода: куда записывается перевод ---

def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def get_export_root(conn: sqlite3.Connection) -> str | None:
    """Папка, куда записывали перевод в прошлый раз.

    Хранится отдельно от `ru_root`: та — источник импорта, и по умолчанию
    писать поверх неё значит затирать дерево, из которого читали.
    """
    return _meta(conn, "export_root")


def set_export_root(conn: sqlite3.Connection, path: Path | str) -> None:
    _set_meta(conn, "export_root", str(path))


# --- формат локализации и кодировка ---

def get_loc_format(conn: sqlite3.Connection) -> str | None:
    """Формат файлов проекта: `yml` или `csv`. None — ещё не определён.

    Определяется при первом сканировании по содержимому дерева и с тех пор
    берётся отсюда. Хранить, а не переопределять каждый раз, нужно ради
    экспорта: дерево оригинала может стать недоступным (диск отключили, мод
    снесли), а записывать перевод всё равно надо в том формате, в каком его
    читали, — угадывать по остаткам поздно.
    """
    return _meta(conn, "loc_format")


def set_loc_format(conn: sqlite3.Connection, format_id: str) -> None:
    _set_meta(conn, "loc_format", format_id)


def get_loc_encoding(conn: sqlite3.Connection) -> str | None:
    """Кодировка дерева перевода. None — формат обходится одной (utf-8 с BOM).

    Нужна старому формату: ваниль лежит в cp1252, русский перевод — в cp1251, и
    записать его в другой кодировке значит отдать игре мусор.
    """
    return _meta(conn, "loc_encoding")


def set_loc_encoding(conn: sqlite3.Connection, encoding: str) -> None:
    _set_meta(conn, "loc_encoding", encoding)


def get_source_encoding(conn: sqlite3.Connection) -> str | None:
    """Кодировка дерева **оригинала** — она бывает другой, чем у перевода.

    Хранится отдельно не для симметрии: экспорт достраивает строку по файлу
    оригинала (там лежат прочие языки), и прочти он ванильный cp1252 как
    cp1251, французское `Reconquête` превратилось бы в `Reconquкte` — причём
    молча, потому что такая строка прекрасно записывается обратно.
    """
    return _meta(conn, "loc_encoding_src")


def set_source_encoding(conn: sqlite3.Connection, encoding: str) -> None:
    _set_meta(conn, "loc_encoding_src", encoding)


def get_last_export_at(conn: sqlite3.Connection) -> str | None:
    return _meta(conn, "last_export_at")


def set_last_export_at(conn: sqlite3.Connection, when: str | None = None) -> None:
    _set_meta(conn, "last_export_at",
              when or datetime.now().strftime("%Y-%m-%d %H:%M"))


# --- разовая уборка строк без переводимого текста ---

def get_auto_ignore_done(conn: sqlite3.Connection) -> bool:
    """Проходил ли по проекту разовый авто-игнор строк из одной разметки.

    Уборка идёт при открытии проекта и заведена ради проектов, созданных
    прежними версиями. Без этой отметки она шла бы каждый раз — и отменённая
    через Ctrl+Z возвращалась бы при следующем открытии. Отмена, которую
    переигрывают за спиной, учит не доверять отмене вообще.

    Сканирование отметку не смотрит и не ставит: оно приносит новые ключи, и
    убирать из них теговые — его обычная работа, а не разовая уборка.
    """
    return _meta(conn, "auto_ignore_done") == "1"


def set_auto_ignore_done(conn: sqlite3.Connection) -> None:
    _set_meta(conn, "auto_ignore_done", "1")


# --- настройка проверок: слой проекта ---

def get_qa_overlay(conn: sqlite3.Connection) -> dict:
    """Правки набора правил, сделанные для этого проекта.

    Живёт в `project_meta`, а не в отдельной таблице: миграция схемы ради
    одной строки JSON не нужна, и настройка уезжает вместе с файлом проекта —
    ровно как список подключённых баз.
    """
    raw = _meta(conn, "qa_overlay")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def set_qa_overlay(conn: sqlite3.Connection, overlay: dict | None) -> None:
    from pdxloc.core import qa_rules

    if overlay is None or qa_rules.is_empty_overlay(overlay):
        conn.execute("DELETE FROM project_meta WHERE key = 'qa_overlay'")
        conn.commit()
        return
    _set_meta(conn, "qa_overlay", json.dumps(overlay, ensure_ascii=False))


def project_tm_paths(conn: sqlite3.Connection) -> list[Path]:
    """Пути включённых баз: сперва загон своей игры, затем корень Bdd.

    В проекте хранится только имя файла — так проект остаётся переносимым.
    Искать приходится в двух местах: базы, собранные до появления загонов,
    лежат в корне, и потерять их из-за переезда папок нельзя.
    """
    folders = [settings.bdd_pen(game(conn)), settings.bdd_dir()]
    paths: list[Path] = []
    for name in get_tm_sources(conn):
        for folder in folders:
            if (folder / name).is_file():
                paths.append(folder / name)
                break
    return paths


def attach_tm_sources(conn: sqlite3.Connection, tm_paths: list[Path]) -> list[str]:
    """Подключить базы на чтение и пересобрать представление tm_all.

    Представление временное, то есть живёт в пределах соединения: фоновому
    сканеру нужно вызывать open_project самому, а не получать чужой connect.
    """
    for row in conn.execute("PRAGMA database_list").fetchall():
        if row[1].startswith("tm"):
            conn.execute(f"DETACH DATABASE {row[1]}")
    conn.execute("DROP VIEW IF EXISTS tm_all")

    parts = [db_module.TM_VIEW_BASE]
    attached: list[str] = []
    for i, path in enumerate(tm_paths):
        path = Path(path)
        if not path.is_file():
            continue
        meta = tm_meta(path)
        if meta is None:
            continue
        alias = f"tm{i}"
        try:
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (_uri(path, "ro"),))
        except sqlite3.Error:
            continue
        origin = meta.get("name") or path.stem
        prio = KIND_PRIORITY.get(meta.get("kind", "import"), 5)
        # идентификаторы подключённых баз делаем отрицательными: нумерация в
        # каждом файле своя, и без этого удаление чужой записи стёрло бы свою
        # с тем же номером
        parts.append(
            f"SELECT -(id + {(i + 1) * 10_000_000}) AS id, "
            "en_hash, en_text, ru_text, source, key, updated_at, "
            f"'{origin.replace(chr(39), chr(39) * 2)}' AS origin, 0 AS editable, "
            f"{prio} AS prio FROM {alias}.tm_entries")
        attached.append(origin)
    conn.execute("CREATE TEMP VIEW tm_all AS " + " UNION ALL ".join(parts))
    return attached


def attached_tm_paths(conn: sqlite3.Connection) -> list[Path]:
    """Файлы подключённых баз памяти — чтобы повторить набор в другом потоке.

    Представление `tm_all` временное, то есть живёт в пределах соединения.
    Фоновый счёт по памяти переводов открывает своё соединение и обязан собрать
    тот же набор баз заново; список путей — всё, что для этого нужно.
    """
    found: list[Path] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        alias, path = row[1], row[2]
        if alias.startswith("tm") and path:
            found.append(Path(path))
    return found


@dataclass
class AttachedTm:
    """Подключённая база для поиска похожих строк."""

    alias: str            # tm0, tm1 … — по нему адресуются таблицы базы
    origin: str           # имя базы, как его видит пользователь
    prio: int             # приоритет источника, как в tm_all
    id_offset: int        # смещение идентификаторов, чтобы совпадало с tm_all
    has_fts: bool         # построен ли индекс похожих строк


def attached_tm_bases(conn: sqlite3.Connection) -> list[AttachedTm]:
    """Подключённые базы с признаком «есть ли индекс похожих строк».

    Поиск похожих идёт по каждой базе отдельно (индекс живёт внутри неё), а не
    через объединяющее представление tm_all, поэтому нужны сами алиасы.
    """
    from pdxloc.core import tm_import

    bases: list[AttachedTm] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        alias, path = row[1], row[2]
        if not alias.startswith("tm") or not path:
            continue
        meta = tm_meta(Path(path)) or {}
        index = int(alias[2:]) if alias[2:].isdigit() else 0
        bases.append(AttachedTm(
            alias=alias,
            origin=meta.get("name") or Path(path).stem,
            prio=KIND_PRIORITY.get(meta.get("kind", "import"), 5),
            id_offset=(index + 1) * 10_000_000,
            has_fts=tm_import.has_fts_index(conn, alias),
        ))
    return bases



"""Игры Paradox: формат локализации у них один, а языки и загоны — разные.

Зачем понадобился реестр. Формат `.yml` с BOM и заголовком `l_<язык>:` одинаков
у всей серии, поэтому переводить моды к Stellaris или HOI4 приложение умеет и
так. Не хватало одного: **сказать, к какой игре относится проект**. Без этого
базы памяти разных игр лежат общей кучей и подсказывают ванильные строки CK3
переводчику Victoria 3, а списки языков предлагают папки, которых у игры нет.

Приём взят у ESP/ESM Translator (там «Game selection» и свои базы на игру):
проект и базы живут в загоне своей игры и не смешиваются.

Набор языковых папок у каждой игры свой, и это не догадка: сверено с
`game_supported_languages.json` из ModTranslationHelper 1.4.3 — единственного
инструмента серии, который эти списки уже собрал.

**Своя игра** заводится свободным именем: формат общий, и запрещать CK2,
Victoria 2 или что-то ещё не за что. У неё общий список папок
(`languages.PARADOX_LANGUAGES`) — какие языки понимает чужая игра, приложению
неоткуда знать.

Названия игр **не переводятся** — это имена продуктов, как и название самого
приложения (см. «Язык интерфейса» в ARCHITECTURE.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from pdxloc.core.languages import PARADOX_LANGUAGES


@dataclass(frozen=True, slots=True)
class Game:
    id: str                      # хранится в файле проекта и в базе памяти
    title: str                   # показывается человеку
    folder: str                  # имя загона на диске
    languages: tuple[str, ...]   # папки локализации, которые понимает игра


CK3 = "ck3"

GAMES: dict[str, Game] = {g.id: g for g in (
    # Порядок значим: первая игра — предложенная по умолчанию, и это по-прежнему
    # CK3, из перевода модов к которой приложение и выросло.
    Game("ck3", "Crusader Kings III", "CK3",
         ("english", "french", "german", "korean", "russian", "simp_chinese",
          "spanish")),
    # CK2 — единственная здесь игра прежнего поколения движка: её локализация
    # лежит в CSV, где язык не папка, а колонка (см. `core/paradox_csv.py`).
    # Русского в её формате нет вовсе — ни в одной шапке ванильных файлов нет
    # RUSSIAN, — поэтому в списке его нет и здесь: перевод на язык, которого
    # игра не знает, задаётся локалью проекта, а лечь ему всё равно в колонку
    # английского.
    Game("ck2", "Crusader Kings II", "CK2",
         ("english", "french", "german", "spanish")),
    Game("eu4", "Europa Universalis IV", "EU4",
         ("english", "french", "german", "spanish")),
    # EU5 вышла позже ModTranslationHelper, сверить её список не с чем, поэтому
    # у неё общий набор папок серии. Лишняя папка в списке ничего не ломает:
    # коробка языков редактируемая, и лишний пункт человек просто не выберет —
    # а вот недостающий заставил бы вписывать язык руками.
    Game("eu5", "Europa Universalis V", "EU5", tuple(PARADOX_LANGUAGES)),
    # Корейский и китайский добавлены не по списку ModTranslationHelper, а по
    # самой игре: в `localisation/languages.yml` установленной HOI4 они есть, и
    # папки под них лежат рядом с остальными. Список конкурента собран раньше и
    # с тех пор отстал — а недостающая папка заставила бы вписывать язык руками.
    Game("hoi4", "Hearts of Iron IV", "HOI4",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "russian", "simp_chinese", "spanish")),
    Game("stellaris", "Stellaris", "Stellaris",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "simp_chinese", "russian", "spanish")),
    Game("vic3", "Victoria 3", "Victoria 3",
         ("english", "braz_por", "french", "german", "japanese", "korean",
          "polish", "russian", "simp_chinese", "spanish", "turkish")),
    Game("imperator", "Imperator: Rome", "Imperator",
         ("english", "french", "german", "russian", "simp_chinese", "spanish")),
)}

ORDER: tuple[str, ...] = tuple(GAMES)


def slug(name: str) -> str:
    """Имя своей игры → идентификатор для файла проекта.

    Латиницей и без пробелов: значение попадает в файл проекта, в базу памяти и
    в имя папки, а эти три места переживут смену раскладки и переезд на другую
    файловую систему только в таком виде.
    """
    out = "".join(c if c.isalnum() and c.isascii() else "_" for c in name.lower())
    out = "_".join(part for part in out.split("_") if part)[:32]
    if not out or out in GAMES:
        # «свой ck3» не должен притворяться встроенным: у того свой набор языков
        out = f"{out}_own" if out else "game"
    return out


def get(game_id: str, title: str = "") -> Game:
    """Игра по идентификатору. Незнакомая — своя, с общим набором языков.

    Незнакомый идентификатор не ошибка: он приезжает из файла проекта, который
    мог быть заведён и в новой версии приложения, и своей игрой.

    Загон своей игры зовётся **как её идентификатор**, а не как введённое имя:
    имя в файле проекта не хранится, и по папке «Victoria 2» опознать проект
    `victoria_2` было бы уже нечем. Слаг для того и собран из латиницы, чтобы
    годиться в имя папки.
    """
    known = GAMES.get(game_id)
    if known is not None:
        return known
    return Game(game_id, title or game_id, game_id, tuple(PARADOX_LANGUAGES))


def title(game_id: str) -> str:
    return get(game_id).title


def languages(game_id: str) -> tuple[str, ...]:
    return get(game_id).languages


def folder(game_id: str) -> str:
    return get(game_id).folder


def by_folder(name: str) -> str | None:
    """Идентификатор игры по имени загона. `None` — папка не загон.

    Нужен защите: по папке, в которой лежит файл проекта, надо понять, чей это
    загон, — и промолчать, если папка вообще не про игры.
    """
    for game in GAMES.values():
        if game.folder.casefold() == name.casefold():
            return game.id
    return None

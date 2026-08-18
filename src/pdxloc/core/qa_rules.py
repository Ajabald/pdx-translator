"""Реестр правил проверки: что проверяем, насколько строго и с какими послаблениями.

Зачем понадобился. Замеры на живом переводе (136 113 строк) показали, что
проверка ругается втрое чаще, чем есть ошибок: 18 527 замечаний о скобках, из
которых настоящих ~20%, потому что переводчик оборачивает подстановку в
`Concept(…)` ради склонения — штатный приём, а не опечатка. Подстраивать
перевод под проверку — хвост виляет собакой; правильно настроить проверку.

Устройство гибридное, и это осознанно:

* **встроенные правила** — функции с параметрами. Именно параметры, а не
  «свои регулярки», убирают измеренный шум: девять галок против десятков тысяч
  ложных срабатываний;
* **пользовательские правила** — шесть декларативных видов (`KINDS`). Полностью
  декларативный язык для встроенных был бы самообманом: на «пропущен пробел
  перед подстановкой» и «такой же оригинал переведён иначе» он выродился бы в
  поле, куда вписывают имя питоновской функции.

И то и другое живёт в одном наборе с одинаковой схемой, одинаково включается и
одинаково показывается. Границы пользователь видеть не должен.

Значения параметров по умолчанию воспроизводили поведение до появления реестра.
Два из них с тех пор изменены — `edge_space.compare_with_source` и
`unbalanced_quotes.only_if_source_balanced`: замер показал, что 93% и 74%
срабатываний приходились на пробел и кавычку, которые стоят в самом оригинале.
Оба дефолта только гасят срабатывания и ни одного не добавляют (проверяется
`test_qa_defaults.py`), поэтому смена безопасна.

Поверх набора ложатся **оверлеи** — дельты, а не полные дампы. Слоёв два,
глобальный и проектный; порядок применения: встроенные значения → пресет и
правки глобального слоя → пресет и правки проекта. Дельта важна: полный дамп
заморозил бы набор на версии приложения, в которой его сохранили, и новые
правила с починенными дефолтами до пользователя бы не доехали.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from collections.abc import Callable, Mapping

from pdxloc.core import inflections, markup
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITIES = (ERROR, WARNING, INFO)
SEVERITY_RANK = {ERROR: 0, WARNING: 1, INFO: 2}

BUILTIN = "builtin"

# Сколько времени своё правило вправе потратить на ОДНУ строку, прежде чем его
# погасят до конца прохода.
#
# Повод — катастрофический бэктрекинг: `(\w+)+$` на длинной строке считается
# минутами, а проход идёт по сотне тысяч строк. Полсекунды на строку — это уже
# на три порядка больше, чем у любого честного правила, так что ложных
# срабатываний ждать неоткуда.
#
# **Чего это не даёт, и обещать обратное было бы неправдой.** Одиночный
# зависший вызов `re` так не прервать: таймаута у модуля нет, сигналы на
# Windows не работают, а сторонний движок сломал бы принцип единственной
# зависимости. Защита здесь от «правило испортило весь проход», а не от
# «правило повесило приложение». Второе ловится раньше — `regex_warning`
# предупреждает в окне правил ещё до запуска.
SLOW_RULE_SECONDS = 0.5

# Категории — порядок задаёт порядок групп в окне правил
CATEGORIES: dict[str, str] = {
    "markup": QT_TRANSLATE_NOOP("QaRules", "Markup"),
    "format": QT_TRANSLATE_NOOP("QaRules", "Formatting"),
    "typography": QT_TRANSLATE_NOOP("QaRules", "Typography"),
    "russian": QT_TRANSLATE_NOOP("QaRules", "Target language"),
    "consistency": QT_TRANSLATE_NOOP("QaRules", "Consistency"),
    "length": QT_TRANSLATE_NOOP("QaRules", "Length"),
    "custom": QT_TRANSLATE_NOOP("QaRules", "Own rules"),
}


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    title: str
    category: str
    message: str
    severity: str = WARNING
    enabled: bool = True
    kind: str = BUILTIN
    params: Mapping = field(default_factory=dict)
    note: str = ""
    # Язык перевода, к которому правило относится. Пусто — любой. Заведено
    # ради `glued_markup` и `linking_calque`: оба про русскую грамматику, и
    # французу они выдали бы замечания про склонение на ровном месте.
    locale: str = ""
    # Примеры работают самопроверкой: и в окне правил, и в pytest. Приём
    # подсмотрен у LanguageTool, где каждое правило обязано нести пример.
    example_ok: tuple[tuple[str, str], ...] = ()      # (оригинал, перевод) — молчит
    example_bad: tuple[tuple[str, str], ...] = ()     # (оригинал, перевод) — срабатывает
    origin: str = BUILTIN

    def with_params(self, **changes) -> Rule:
        return replace(self, params={**self.params, **changes})

    # Подписи переводятся здесь, а не в окне правил: к ним ходят и отчёт F6,
    # и подсказка колонки «!», и разошлись бы они мгновенно. Текст своего
    # правила не переводится вовсе: его написал пользователь, и совпадение с
    # английской строкой интерфейса подменяло бы его чужим переводом.
    def _text(self, source: str) -> str:
        if not source:
            return ""
        return source if self.origin != BUILTIN else translate("QaRules", source)

    def title_text(self) -> str:
        return self._text(self.title)

    def message_text(self) -> str:
        return self._text(self.message)

    def note_text(self) -> str:
        return self._text(self.note)


# --- вспомогательное -----------------------------------------------------

RE_ESCAPE_SEQ = re.compile(r"\\[nrt]")
# Вставка, приклеенная к целому слову: «дома[GetPlayer…]» → в игре «домаСтарк»
RE_GLUED_TAIL = r"\[[^\[\]]*\]"
# Голова вызова внутри скобки: [Concept('faith','вера')|E] → Concept
RE_HEAD = re.compile(r"^\[\s*([A-Za-z_][A-Za-z0-9_]*)")
# То же имя, но без скобки слева — им `tail_of` разбирает последнее звено
RE_HEAD_BARE = re.compile(r"^[?]?([A-Za-z_][A-Za-z0-9_]*)")
# Флаги оформления в конце токена: [men_at_arms|E] → [men_at_arms]
RE_TOKEN_FLAGS = re.compile(r"\|[^\[\]|]*(?=\]$)")

DEFAULT_PAIRS = (("«", "»"), ("(", ")"), ("[", "]"), ("{", "}"))


def _multiset(pattern: re.Pattern, text: str) -> Counter:
    return Counter(pattern.findall(text))


def head_of(token: str) -> str:
    """Имя функции внутри скобки — по нему отличают приём от опечатки."""
    match = RE_HEAD.match(token)
    return match.group(1) if match else ""


def tail_of(token: str) -> str:
    """Имя вызываемой функции — последнее звено цепочки внутри скобки.

    `head_of` смотрит на первое слово, и в CK3 это и есть функция
    (`[GetTrait('x').GetName]` → `GetTrait`). В HOI4 первым стоит область
    видимости — тег страны или `ROOT`/`FROM`, — а функция оказывается в конце:
    `[JAP.GetAdjRuLower]`. Русская локализация HOI4 склоняет ровно этими
    хвостами, и без них замену `GetAdjective` → `GetAdjRuLower` не отличить от
    потерянной ссылки: 5 028 строк ванильного перевода против 746 настоящих
    расхождений.
    """
    inner = token.strip("[]").split("|")[0]     # флаги оформления не в счёт
    last = inner.split(".")[-1].strip()
    match = RE_HEAD_BARE.match(last)
    return match.group(1) if match else ""


def _drop_flags(token: str) -> str:
    return RE_TOKEN_FLAGS.sub("", token)


def _tokens(pattern: re.Pattern, text: str, *, ignore_flags: bool) -> Counter:
    found = pattern.findall(text)
    if ignore_flags:
        found = [_drop_flags(t) for t in found]
    return Counter(found)


def _differs(en_tokens: Counter, ru_tokens: Counter, *,
             compare: str, ignore_extra_heads: tuple[str, ...],
             allow_replacement: bool = False,
             ignore_extra_tails: tuple[str, ...] = (),
             allow_extra: bool = False) -> bool:
    """Расходятся ли наборы токенов с учётом послаблений."""
    if compare == "count":
        return sum(en_tokens.values()) != sum(ru_tokens.values())
    extra = ru_tokens - en_tokens          # появилось в переводе
    missing = en_tokens - ru_tokens        # потерялось при переводе

    if ignore_extra_heads or ignore_extra_tails:
        # Обёртка ради грамматики — не расхождение: переводчик добавил
        # Concept(…)/Select_CString(…), чтобы просклонять термин. В HOI4 то же
        # самое делается не обёрткой, а склоняющей функцией на конце цепочки
        # ([JAP.GetAdjRuLower] вместо [JAP.GetAdjective]) — отсюда второй
        # список, по хвостам.
        forgiven = Counter({t: n for t, n in extra.items()
                            if head_of(t) in ignore_extra_heads
                            or tail_of(t) in ignore_extra_tails})
        extra -= forgiven
        if allow_replacement and forgiven and not extra:
            # Обёртка не «сверх», а «вместо»: английское [CharAreIs(actor)]
            # заменено на [Select_CString(actor.IsFemale, 'ведьма', 'колдун')],
            # потому что русскому нужен род. Замер на живом переводе: таких
            # случаев 59% всех расхождений по скобкам — больше, чем чистых
            # обёрток. Гасим столько потерянных токенов, сколько добавлено
            # обёрток: замена один к одному прощается, настоящая потеря — нет.
            budget = sum(forgiven.values())
            for token in list(missing):
                taken = min(budget, missing[token])
                missing[token] -= taken
                budget -= taken
                if missing[token] <= 0:
                    del missing[token]
                if not budget:
                    break

    if allow_extra:
        # Подстановка, которой в оригинале не было, игру не ломает: она
        # валидна, просто текста стало больше. Русскому это нужно часто —
        # «Ты славно сража[X.GetLasLsya], [X.GetFirstName].» там, где по-английски
        # обращение опущено. Потерянная подстановка, наоборот, оставляет в игре
        # дыру, и её этот параметр не трогает.
        extra = Counter()

    if compare == "set":
        return bool(set(extra) or set(missing))
    return bool(extra or missing)


@lru_cache(maxsize=64)
def _glue_re(min_word_len: int) -> re.Pattern:
    return re.compile(rf"[^\W\d_]{{{min_word_len},}}{RE_GLUED_TAIL}")


@lru_cache(maxsize=64)
def _calque_re(verbs: tuple[str, ...]) -> re.Pattern:
    """Связка + подстановка. Глаголы — фрагменты регулярки, не простые слова.

    Отрицание отсекаем: «целью не может быть [Имя]» ставит подстановку в
    позицию подлежащего, и именительный падеж там правилен.
    """
    return re.compile(r"(?<!не )\b(?:" + "|".join(verbs) + r")"
                      r"\s*\[(?:Get|[A-Z_]+\.Get)")


def _returns_word_ending(token: str, wrappers: tuple[str, ...],
                         suffixes: tuple[str, ...],
                         calls: tuple[str, ...] = ()) -> bool:
    """Подстановка возвращает окончание слова, а не имя.

    К таким её и дописывают вплотную, и это норма, а не потеря пробела:
    `Select_CString(X.IsFemale, 'а', '')` превращает «даровал» в «даровала», а
    функции с суффиксом `_END` (`GetAnimalType_RU_Acc_END`) заведены
    переводчиками ровно под падежные окончания.

    В HOI4 то же самое делает сама игра, отдельными функциями:
    «объявил[CHI.GetVerbGendEndA_RU]» — 1 097 таких склеек в ванильном русском
    переводе. Их узнаём по имени вызова (`calls`), а не по аргументу.
    """
    if head_of(token) in wrappers:
        return True
    if tail_of(token) in calls:
        return True
    return any(f"{s}'" in token or f'{s}"' in token for s in suffixes)


def _glued_count(text: str, params: Mapping) -> int:
    text = RE_ESCAPE_SEQ.sub(" ", text)     # «\n» — не буква n перед скобкой
    wrappers = tuple(params.get("ending_wrappers", ()))
    suffixes = tuple(params.get("ending_suffixes", ()))
    calls = tuple(params.get("ending_calls", ()))
    inside_word_ok = bool(params.get("allow_inside_word"))
    pattern = _glue_re(int(params.get("min_word_len", 3)))
    count = 0
    for match in pattern.finditer(text):
        chunk = match.group(0)
        if _returns_word_ending(chunk[chunk.index("["):], wrappers, suffixes, calls):
            continue
        # Подстановка не перед словом, а внутри него: «анти[X.GetAdjective]ое»
        # — приставка слева, окончание справа, и пробелу там взяться неоткуда.
        # 279 склеек ванильного русского HOI4 против 5 настоящих потерь пробела.
        after = text[match.end():match.end() + 1]
        if inside_word_ok and after.isalpha():
            continue
        count += 1
    return count


def _unbalanced(text: str, pairs) -> bool:
    for left, right in pairs:
        if text.count(left) != text.count(right):
            return True
    return text.count('"') % 2 == 1


# --- сами проверки -------------------------------------------------------
#
# Каждая получает (оригинал, перевод, параметры) и отвечает «есть замечание».


def _check_dollar(en: str, ru: str, p: Mapping) -> bool:
    flags = bool(p.get("ignore_flags"))
    en_tokens = _tokens(markup.pattern("dollar"), en, ignore_flags=flags)
    ru_tokens = _tokens(markup.pattern("dollar"), ru, ignore_flags=flags)
    if p.get("only_if_all_lost"):
        # Замер на живом переводе развёл два разных случая: 789 строк, где в
        # переводе не осталось ни одной переменной (дыра в тексте прямо в игре),
        # и 624, где набор просто отличается — там переводчик чаще всего
        # переставил или заменил подстановку осознанно. Параметр гасит вторые,
        # не трогая первые; выключен по умолчанию — замена бывает и ошибкой.
        return bool(en_tokens) and not ru_tokens
    return _differs(en_tokens, ru_tokens,
                    compare=p.get("compare", "multiset"), ignore_extra_heads=(),
                    allow_extra=bool(p.get("allow_extra")))


def _check_icon(en: str, ru: str, p: Mapping) -> bool:
    """Иконки обеих записей — по каждой отдельно.

    Не одним общим мультимножеством: `£gold£`, замененное на `@gold!`, в общем
    мешке дало бы равенство, а это разные токены разных игр, и подмена одного
    другим — как раз ошибка.
    """
    return any(_multiset(markup.pattern(token_id), en)
               != _multiset(markup.pattern(token_id), ru)
               for token_id in ("icon_pound", "icon_var", "icon_at"))


def _check_color(en: str, ru: str, p: Mapping) -> bool:
    """Цветовые коды HOI4/EU4/Stellaris — по каждому виду отдельно.

    Раздельно, как и у иконок: `§Y` (жёлтый) вместо `§R` (красный) — не то же
    самое, что «цвет на месте», а закрывающий `§!` без открывающего красит
    остаток строки целиком. `compare: count` оставляет только счёт, если
    переводчик осознанно меняет оттенки.
    """
    compare = p.get("compare", "multiset")
    for token_id in ("color_open", "color_close", "color_script"):
        pattern = markup.pattern(token_id)
        if _differs(_multiset(pattern, en), _multiset(pattern, ru),
                    compare=compare, ignore_extra_heads=()):
            return True
    return False


def _check_grammar(en: str, ru: str, p: Mapping) -> bool:
    """Грамматика Stellaris: тег или вариант, потерянный при переводе.

    Сравнение одностороннее, и это не послабление, а устройство системы:
    варианты для падежей дописывает **переводчик** (6 327 строк русского дерева
    против 463 английского), поэтому добавленное расхождением не считается.
    А вот потерянный `&!fem` меняет род имени во всех фразах, куда оно
    подставится, — и заметить это в игре можно только случайно.
    """
    for token_id in ("grammar_tags", "grammar_variant"):
        pattern = markup.pattern(token_id)
        if _differs(_multiset(pattern, en), _multiset(pattern, ru),
                    compare=p.get("compare", "multiset"),
                    ignore_extra_heads=(), allow_extra=True):
            return True
    return False


def _check_fmt(en: str, ru: str, p: Mapping) -> bool:
    pattern = markup.pattern("fmt_open")
    fold = bool(p.get("case_insensitive"))
    allowed = {t.lower() if fold else t for t in p.get("allow_extra_tags", ())}
    ignored = {t.lower() if fold else t for t in p.get("ignore_tags", ())}

    def bag(text: str) -> Counter:
        found = pattern.findall(text)
        if fold:
            found = [t.lower() for t in found]
        return Counter(t for t in found if t not in ignored)

    en_tags, ru_tags = bag(en), bag(ru)
    extra = ru_tags - en_tags
    if allowed:
        # Переводчик дописал #L ради падежа — приём, а не потеря тега
        extra = Counter({t: n for t, n in extra.items() if t not in allowed})
    return bool(extra or (en_tags - ru_tags))


def _check_fmt_broken(en: str, ru: str, p: Mapping) -> bool:
    opens, closes = markup.pattern("fmt_open"), markup.pattern("fmt_close")
    # Только когда оригинал закрыт: в CK3 #weak в конце строки закрывать не
    # обязательно, и несбалансирован бывает сам мод.
    return (len(opens.findall(en)) == len(closes.findall(en))
            and len(opens.findall(ru)) != len(closes.findall(ru)))


def _check_brackets(en: str, ru: str, p: Mapping) -> bool:
    pattern = markup.pattern("bracket")
    flags = bool(p.get("ignore_flags"))
    return _differs(_tokens(pattern, en, ignore_flags=flags),
                    _tokens(pattern, ru, ignore_flags=flags),
                    compare=p.get("compare", "multiset"),
                    ignore_extra_heads=tuple(p.get("ignore_extra_heads", ())),
                    ignore_extra_tails=tuple(p.get("ignore_extra_tails", ())),
                    allow_replacement=bool(p.get("allow_replacement")),
                    allow_extra=bool(p.get("allow_extra")))


def _delta_fails(delta: int, p: Mapping) -> bool:
    """Расхождение в числе токенов с учётом допуска и направления.

    `delta` — сколько токенов потерялось: положительное значит «в переводе
    меньше». Отдельной функцией, потому что тем же самым меряет и
    пользовательский вид `token_count`.
    """
    tolerance = int(p.get("tolerance", 0))
    direction = p.get("direction", "any")
    if direction == "fewer":        # ругаться только на потерянные токены
        return delta > tolerance
    if direction == "more":
        return -delta > tolerance
    return abs(delta) > tolerance


def _check_newline(en: str, ru: str, p: Mapping) -> bool:
    pattern = markup.pattern("newline")
    return _delta_fails(len(pattern.findall(en)) - len(pattern.findall(ru)), p)


def _check_same_as_en(en: str, ru: str, p: Mapping) -> bool:
    return ru == en and len(en) >= int(p.get("min_length", 0))


def _check_edge_space(en: str, ru: str, p: Mapping) -> bool:
    if p.get("compare_with_source"):
        # Краевой пробел бывает и в оригинале — так склеивают строки в игре
        return (ru != ru.strip()) and (en == en.strip())
    return ru != ru.strip()


def _check_double_space(en: str, ru: str, p: Mapping) -> bool:
    pattern = markup.pattern("newline")
    # Абзацный разрыв \n\n — не двойной пробел: считаем внутри отрезков
    hit = any("  " in part for part in pattern.split(ru.strip()))
    if hit and p.get("ignore_if_in_source"):
        return not any("  " in part for part in pattern.split(en.strip()))
    return hit


def _check_unbalanced(en: str, ru: str, p: Mapping) -> bool:
    pairs = [tuple(pair) for pair in p.get("pairs", DEFAULT_PAIRS)]
    text_ru, text_en = ru, en
    if p.get("strip_markup_first"):
        text_ru, text_en = markup.strip_markup(ru), markup.strip_markup(en)
    if not _unbalanced(text_ru, pairs):
        return False
    if p.get("only_if_source_balanced") and _unbalanced(text_en, pairs):
        return False        # несбалансирован сам оригинал — перевод ни при чём
    return True


def _check_glued(en: str, ru: str, p: Mapping) -> bool:
    # Сравниваем с оригиналом: «[command_modifier_i|E]Minimum» — законная
    # склейка, и перевод вправе её унаследовать.
    return _glued_count(ru, p) > _glued_count(en, p)


def _check_calque(en: str, ru: str, p: Mapping) -> bool:
    # С оригиналом не сравниваем: по-английски «tend to be [Trait]» безупречно,
    # ломается только русский текст.
    verbs = tuple(p.get("verbs", ()))
    return bool(verbs) and bool(_calque_re(verbs).search(ru))


def _check_len_ratio(en: str, ru: str, p: Mapping) -> bool:
    if ru == en:
        return False
    en_clean, ru_clean = markup.strip_markup(en), markup.strip_markup(ru)
    if len(en_clean) < int(p.get("min_source_len", 10)) or not ru_clean:
        return False
    ratio = len(ru_clean) / len(en_clean)
    return ratio < float(p.get("min_ratio", 0.5)) or ratio > float(p.get("max_ratio", 2.0))


CHECKS: dict[str, Callable[[str, str, Mapping], bool]] = {
    "dollar_mismatch": _check_dollar,
    "icon_mismatch": _check_icon,
    "color_mismatch": _check_color,
    "grammar_mismatch": _check_grammar,
    "fmt_mismatch": _check_fmt,
    "fmt_broken": _check_fmt_broken,
    "brackets_mismatch": _check_brackets,
    "newline_mismatch": _check_newline,
    "same_as_en": _check_same_as_en,
    "edge_space": _check_edge_space,
    "double_space": _check_double_space,
    "unbalanced_quotes": _check_unbalanced,
    "glued_markup": _check_glued,
    "linking_calque": _check_calque,
    "len_ratio": _check_len_ratio,
}

# Проверки, которым нужен не одна строка, а весь проект
PROJECT_WIDE = ("inconsistent",)
# Пустой перевод — особый случай: отвечать на него всеми остальными
# замечаниями бессмысленно, поэтому проверка обрывает разбор строки
EMPTY = "empty_translated"

CALQUE_VERBS = (
    r"склонн\w+\s+быть", r"мог(?:ут|ла|ли)\s+быть",
    "бывают", "бывает", "рождаются", "рождается",
    "считаются", "считается", "слывут", "славятся",
)


# --- виды пользовательских правил ---------------------------------------
#
# Шесть видов, а не язык описания правил. Причина та же, по которой встроенные
# правила остались функциями: настоящие проверки опираются на разбор скобок, на
# соседние строки проекта, на реестр разметки — выразить это декларацией нельзя,
# и попытка выродилась бы в поле «имя питоновской функции».
#
# Виды покрывают то, что переводчик формулирует сам: «этих символов в переводе
# быть не должно», «сколько таких кусков в оригинале, столько и в переводе»,
# «после такого в оригинале в переводе обязано быть вот такое». Всё остальное —
# повод завести встроенное правило, а не строчку в настройке.

USER = "user"


@lru_cache(maxsize=256)
def _user_re(pattern: str, ignore_case: bool = False) -> re.Pattern | None:
    """Выражение пользователя; `None` — не разбирается.

    Битое выражение гасит своё правило и не трогает остальные: проверка идёт по
    сотне тысяч строк, и падать посреди прохода из-за незакрытой скобки в чужой
    настройке она не имеет права. Что именно не так, показывает окно правил
    (`regex_error`) — там ошибке и место, рядом с полем ввода.
    """
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error:
        return None


def regex_error(pattern: str) -> str:
    """Жалоба разборщика на выражение или пусто, если всё в порядке."""
    if not pattern:
        return ""
    try:
        re.compile(pattern)
    except re.error as e:
        return str(e)
    return ""


# Квантификатор над группой, внутри которой тоже квантификатор: `(\w+)+`,
# `(a*)*`, `(\d+\s?)+`. На строке, которая почти подходит, разборщик перебирает
# экспоненциально много вариантов — секунды на одной строке, а проверка идёт по
# сотне тысяч. Модуль `re` прервать нельзя ничем: ни таймаута, ни сигнала на
# Windows, — поэтому единственная защита в том, чтобы предупредить человека
# раньше, чем он нажмёт F6.
_NESTED_QUANTIFIER = re.compile(r"\((?![?*+])[^()]*[*+][^()]*\)\s*[*+]")


def regex_warning(pattern: str) -> str:
    """Предупреждение о выражении, которое может подвесить проверку.

    Не ошибка: выражение разбирается и, скорее всего, работает. Но правила
    ездят между переводчиками файлом `.pdxqa`, и полученное со стороны правило
    так же способно занять процессор надолго, как и написанное своей рукой.
    """
    if not pattern or regex_error(pattern):
        return ""
    if _NESTED_QUANTIFIER.search(pattern):
        return translate(
            "QaRules",
            "A repetition inside a repeated group — on a long row the check can "
            "take minutes. Consider (?:…) or a stricter pattern.")
    return ""


def _found(pattern: re.Pattern, text: str) -> Counter:
    """Совпадения целиком, а не группы.

    `findall` при скобках в выражении отдаёт группы, и `(\\w+)` вместо
    `(?:\\w+)` менял бы смысл правила молча. Пользователю такое различие знать
    не за чем.
    """
    return Counter(m.group(0) for m in pattern.finditer(text))


def _check_token_multiset(en: str, ru: str, p: Mapping) -> bool:
    rx = _user_re(str(p.get("pattern", "")), bool(p.get("ignore_case")))
    if rx is None:
        return False
    return _differs(_found(rx, en), _found(rx, ru),
                    compare=str(p.get("compare", "multiset")),
                    ignore_extra_heads=())


def _check_token_count(en: str, ru: str, p: Mapping) -> bool:
    rx = _user_re(str(p.get("pattern", "")), bool(p.get("ignore_case")))
    if rx is None:
        return False
    return _delta_fails(sum(1 for _ in rx.finditer(en))
                        - sum(1 for _ in rx.finditer(ru)), p)


def _check_target_regex(en: str, ru: str, p: Mapping) -> bool:
    rx = _user_re(str(p.get("pattern", "")), bool(p.get("ignore_case")))
    if rx is None:
        return False
    hit = bool(rx.search(ru))
    if p.get("mode") == "require":
        return not hit
    if hit and p.get("ignore_if_in_source") and rx.search(en):
        return False
    return hit


def _check_pair_regex(en: str, ru: str, p: Mapping) -> bool:
    """Нашли в оригинале — значит, ждём соответствующее в переводе.

    Приём взят у Okapi CheckMate (там это Patterns): выражение по оригиналу и
    шаблон ответа, куда подставляются группы (`\\1`). Шаблон по умолчанию ищется
    как текст, а не как выражение, — иначе самый очевидный случай ломался бы
    молча: `$\\1$` в роли выражения означает «конец строки, VALUE, конец
    строки» и не совпадёт ни с чем.
    """
    ignore_case = bool(p.get("ignore_case"))
    src = _user_re(str(p.get("source", "")), ignore_case)
    if src is None:
        return False
    template = str(p.get("target", ""))
    as_regex = bool(p.get("target_as_regex"))
    haystack = ru.lower() if ignore_case and not as_regex else ru
    for match in src.finditer(en):
        try:
            wanted = match.expand(template)
        except (re.error, IndexError):
            return False        # шаблон ссылается на группу, которой нет
        if as_regex:
            rx = _user_re(wanted, ignore_case)
            if rx is None or not rx.search(ru):
                return True
        elif (wanted.lower() if ignore_case else wanted) not in haystack:
            return True
    return False


def _check_balance(en: str, ru: str, p: Mapping) -> bool:
    pairs = [(s[0], s[-1]) for s in p.get("pairs", ())
             if isinstance(s, str) and len(s) == 2]
    if not pairs:
        return False
    text_ru, text_en = ru, en
    if p.get("strip_markup_first"):
        text_ru, text_en = markup.strip_markup(ru), markup.strip_markup(en)

    def unbalanced(text: str) -> bool:
        # Одинаковые половинки («"» и «"») считаются на чётность: равенство
        # счётчиков для них выполняется всегда и не значит ничего.
        return any(text.count(left) % 2 == 1 if left == right
                   else text.count(left) != text.count(right)
                   for left, right in pairs)

    if not unbalanced(text_ru):
        return False
    if p.get("only_if_source_balanced") and unbalanced(text_en):
        return False
    return True


def _check_forbidden_chars(en: str, ru: str, p: Mapping) -> bool:
    chars = set(str(p.get("chars", "")))
    if not chars:
        return False
    hit = chars & set(ru)
    if not hit:
        return False
    if p.get("ignore_if_in_source"):
        return not hit <= set(en)
    return True


@dataclass(frozen=True, slots=True)
class Kind:
    """Вид пользовательского правила: чем настраивается и чем проверяет."""

    id: str
    title: str
    hint: str
    defaults: Mapping
    check: Callable[[str, str, Mapping], bool]


KINDS: dict[str, Kind] = {k.id: k for k in (
    Kind(
        id="token_multiset",
        title=QT_TRANSLATE_NOOP("QaRules", "Same set of matches"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "What the expression finds in the original must be found "
                       "in the translation — the same items and as many"),
        defaults={"pattern": "", "compare": "multiset", "ignore_case": False},
        check=_check_token_multiset,
    ),
    Kind(
        id="token_count",
        title=QT_TRANSLATE_NOOP("QaRules", "Same number of matches"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "Only the count is compared, the items themselves may "
                       "differ — for things that get translated"),
        defaults={"pattern": "", "tolerance": 0, "direction": "any",
                  "ignore_case": False},
        check=_check_token_count,
    ),
    Kind(
        id="target_regex",
        title=QT_TRANSLATE_NOOP("QaRules", "Expression in the translation"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "forbid — fires when found, require — fires when missing"),
        defaults={"pattern": "", "mode": "forbid", "ignore_case": False,
                  "ignore_if_in_source": False},
        check=_check_target_regex,
    ),
    Kind(
        id="pair_regex",
        title=QT_TRANSLATE_NOOP("QaRules", "Original → translation"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "For every match in the original the translation must "
                       "contain the answer: groups are substituted into it as \\1"),
        defaults={"source": "", "target": "", "target_as_regex": False,
                  "ignore_case": False},
        check=_check_pair_regex,
    ),
    Kind(
        id="balance",
        title=QT_TRANSLATE_NOOP("QaRules", "Paired characters"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "Two characters per pair: «» or (). Identical halves "
                       "are counted for parity"),
        defaults={"pairs": ["«»"], "only_if_source_balanced": True,
                  "strip_markup_first": False},
        check=_check_balance,
    ),
    Kind(
        id="forbidden_chars",
        title=QT_TRANSLATE_NOOP("QaRules", "Forbidden characters"),
        hint=QT_TRANSLATE_NOOP(
            "QaRules", "Every character listed is forbidden in the translation"),
        defaults={"chars": "", "ignore_if_in_source": False},
        check=_check_forbidden_chars,
    ),
)}

KIND_ORDER: tuple[str, ...] = tuple(KINDS)


def check_of(rule: Rule) -> Callable[[str, str, Mapping], bool] | None:
    """Проверяющая функция правила — своя у встроенного, общая у вида."""
    if rule.kind == BUILTIN:
        return CHECKS.get(rule.id)
    kind = KINDS.get(rule.kind)
    return kind.check if kind is not None else None


def make_user_rule(rule_id: str, kind: str, *, title: str,
                   message: str = "", severity: str = WARNING,
                   category: str = "custom", enabled: bool = True,
                   params: Mapping | None = None, note: str = "",
                   locale: str = "") -> Rule:
    """Своё правило: параметры вида плюс то, что задал пользователь.

    Незнакомые параметры отбрасываются здесь же — как и в оверлее, чтобы
    правило, приехавшее из чужой версии, не таскало за собой поле, которого
    больше нет.
    """
    spec = KINDS[kind]
    known = {k: v for k, v in (params or {}).items() if k in spec.defaults}
    return Rule(
        id=rule_id, title=title,
        # Незнакомая категория увела бы правило из дерева окна целиком: там
        # группы строятся по `CATEGORIES`, и чужая строка не совпала бы ни с одной.
        category=category if category in CATEGORIES else "custom",
        message=message or title,
        severity=severity if severity in SEVERITIES else WARNING,
        enabled=enabled, kind=kind, params={**spec.defaults, **known},
        note=note, locale=locale, origin=USER,
    )


def dump_user_rule(rule: Rule) -> dict:
    """Запись правила для оверлея и файла обмена — целиком, а не дельтой.

    Дельта тут невозможна: у своего правила нет основания, от которого её
    считать. Зато и «новые поля доедут сами» здесь не нужно — поля задаёт
    пользователь.
    """
    return {
        "id": rule.id, "kind": rule.kind, "title": rule.title,
        "message": rule.message, "category": rule.category,
        "severity": rule.severity, "enabled": rule.enabled,
        "params": dict(rule.params), "note": rule.note, "locale": rule.locale,
    }


def load_user_rule(record: Mapping) -> Rule | None:
    """Правило из записи; `None` — запись не понята.

    Молча пропускаем три случая: незнакомый вид (правило из будущей версии),
    подмену встроенного правила (иначе чужой файл мог бы переопределить
    проверку скобок собственным выражением) и запись без имени.
    """
    if not isinstance(record, Mapping):
        return None
    rule_id = str(record.get("id") or "").strip()
    kind = str(record.get("kind") or "")
    if not rule_id or rule_id in BY_ID or kind not in KINDS:
        return None
    params = record.get("params")
    return make_user_rule(
        rule_id, kind,
        title=str(record.get("title") or rule_id),
        message=str(record.get("message") or ""),
        severity=str(record.get("severity") or WARNING),
        category=str(record.get("category") or "custom"),
        enabled=bool(record.get("enabled", True)),
        params=params if isinstance(params, Mapping) else None,
        note=str(record.get("note") or ""),
        locale=str(record.get("locale") or ""),
    )


def user_rules(overlay: Mapping | None) -> tuple[Rule, ...]:
    """Свои правила слоя, в порядке записи."""
    records = (overlay or {}).get("custom")
    if not isinstance(records, (list, tuple)):
        return ()
    loaded = (load_user_rule(r) for r in records)
    return tuple(r for r in loaded if r is not None)


# --- встроенный набор ----------------------------------------------------
#
# Порядок объявления = порядок проверки = порядок кодов в замечаниях.

# Примеры (`example_bad`/`example_ok`) намеренно НЕ переводятся: это не подписи,
# а самопроверка правила. Русские глаголы в примере `linking_calque` обязаны
# заставить правило сработать — переведи их, и правило замолчит на собственном
# примере (это ловит `test_qa_defaults.py`).

BUILTIN_RULES: tuple[Rule, ...] = (
    Rule(
        id=EMPTY, title=QT_TRANSLATE_NOOP("QaRules", "Empty translation"),
        category="consistency", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Status is «translated», but the translation is empty"),
        example_bad=(("Hello", "   "),), example_ok=(("Hello", "Привет"),),
    ),
    Rule(
        id="dollar_mismatch", title=QT_TRANSLATE_NOOP("QaRules", "Variables $…$"),
        category="markup", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Variables $…$ do not match the original"),
        params={"ignore_flags": False, "compare": "multiset",
                "only_if_all_lost": False, "allow_extra": False},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "A lost variable is a hole in the text right in the game. "
                       "Of the hits on a live translation, 56% are exactly that "
                       "and 44% are a differing set — the latter are silenced by "
                       "«only_if_all_lost»"),
        example_bad=(("Cost: $VALUE$", "Цена"),),
        example_ok=(("Cost: $VALUE$", "Цена: $VALUE$"),),
    ),
    Rule(
        id="icon_mismatch", title=QT_TRANSLATE_NOOP("QaRules", "Icons @…! and £…£"),
        category="markup", severity=ERROR,
        message=QT_TRANSLATE_NOOP("QaRules", "Icons do not match the original"),
        note=QT_TRANSLATE_NOOP(
            "QaRules", "@gold! is the CK3 icon. £gold£ belongs to "
                       "EU4/HOI4/Stellaris and never occurs in CK3 — zero "
                       "matches over 440 000 rows — but it is still checked, "
                       "because a translator who saw one elsewhere may type it"),
        example_bad=(("@gold! paid", "уплачено"),
                     ("£gold£ paid", "уплачено")),
        example_ok=(("@gold! paid", "@gold! уплачено"),
                    ("£gold£ paid", "£gold£ уплачено")),
    ),
    Rule(
        id="color_mismatch",
        title=QT_TRANSLATE_NOOP("QaRules", "Colour codes §…§!"),
        category="markup", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Colour codes do not match the original"),
        params={"compare": "multiset"},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "The HOI4/EU4/Stellaris colour: §Y…§!. A lost §! paints "
                       "the rest of the line, a swapped code turns a warning "
                       "green. Quiet on live data: 25 hits over the whole "
                       "vanilla Russian HOI4 (11 290 rows carry a colour)"),
        example_bad=(("§YWarning§!", "Внимание"),),
        example_ok=(("§YWarning§!", "§YВнимание§!"),),
    ),
    Rule(
        id="grammar_mismatch",
        title=QT_TRANSLATE_NOOP("QaRules", "Grammar tags and variants"),
        category="markup", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "A grammar tag or variant of the original was lost"),
        params={"compare": "multiset"},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "The Stellaris 3.6 system: «Empress&!fem,vowel» and "
                       "«A $1$|||vowel:An $1$». Added variants are not counted "
                       "— it is the translator who writes them for cases, "
                       "6 327 rows of the Russian tree against 463 of the "
                       "English one; a lost tag, on the contrary, changes the "
                       "gender of a name everywhere it is substituted"),
        example_bad=(("Empress&!fem", "Императрица"),),
        example_ok=(("Empress&!fem", "Императрица&!fem"),
                    ("Queen", "Королева&!fem|||gen:Королевы")),
    ),
    Rule(
        id="fmt_mismatch", title=QT_TRANSLATE_NOOP("QaRules", "Formatting tags #…"),
        category="format", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "The set of formatting tags differs from the original"),
        params={"allow_extra_tags": [], "ignore_tags": [], "case_insensitive": False},
        example_bad=(("#bold Text#!", "Текст"),),
        example_ok=(("#bold Text#!", "#bold Текст#!"),),
    ),
    Rule(
        id="fmt_broken", title=QT_TRANSLATE_NOOP("QaRules", "Tags not closed"),
        category="format", severity=ERROR,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Tags are closed in the original but not in the translation"),
        example_bad=(("#bold Text#!", "#bold Текст"),),
        example_ok=(("#weak Text", "#weak Текст"),),
    ),
    Rule(
        id="brackets_mismatch",
        title=QT_TRANSLATE_NOOP("QaRules", "Script references [ ]"),
        category="markup",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Script references [ ] differ from the original"),
        params={"ignore_extra_heads": [], "ignore_extra_tails": [],
                "allow_replacement": False, "allow_extra": False,
                "ignore_flags": False, "compare": "multiset"},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "The main source of noise: the translator wraps a "
                       "substitution in Concept(…) to inflect it — that is a "
                       "technique, not a mistake"),
        example_bad=(("Rules [GetName]", "Правит"),),
        example_ok=(("Rules [GetName]", "Правит [GetName]"),),
    ),
    Rule(
        id="newline_mismatch", title=QT_TRANSLATE_NOOP("QaRules", "Line breaks"),
        category="format",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "The number of \\n breaks differs from the original"),
        params={"tolerance": 0, "direction": "any"},
        example_bad=(("One\\ntwo", "Один два"),),
        example_ok=(("One\\ntwo", "Один\\nдва"),),
    ),
    Rule(
        id="same_as_en",
        title=QT_TRANSLATE_NOOP("QaRules", "Translation equals the original"),
        category="consistency",
        message=QT_TRANSLATE_NOOP("QaRules", "The translation matches the original"),
        params={"min_length": 0},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "Normal for names and numbers — such rows are marked "
                       "«Ignore»"),
        example_bad=(("Hello", "Hello"),), example_ok=(("Hello", "Привет"),),
    ),
    Rule(
        id="edge_space", title=QT_TRANSLATE_NOOP("QaRules", "Edge spaces"),
        category="typography",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Extra spaces at the beginning or the end"),
        params={"compare_with_source": True},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "The edge space is in the original too — that is how the "
                       "game glues strings together; on a live translation this "
                       "is 93% of all hits of the rule"),
        example_bad=(("Hello", "Привет "),), example_ok=(("Hello ", "Привет "),),
    ),
    Rule(
        id="double_space", title=QT_TRANSLATE_NOOP("QaRules", "Double spaces"),
        category="typography",
        message=QT_TRANSLATE_NOOP("QaRules", "Double spaces in the translation"),
        params={"ignore_if_in_source": False},
        example_bad=(("Hello world", "Привет  мир"),),
        example_ok=(("Hello\\n\\nworld", "Привет\\n\\nмир"),),
    ),
    Rule(
        id="unbalanced_quotes",
        title=QT_TRANSLATE_NOOP("QaRules", "Unpaired quotes and brackets"),
        category="typography",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Unpaired quotes or brackets in the translation"),
        params={"only_if_source_balanced": True, "strip_markup_first": False},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "The original itself is often unbalanced — on a live "
                       "translation that is 74% of all hits, and the translation "
                       "has nothing to do with it"),
        example_bad=(("A (b) c", "А (б в"),), example_ok=(("A (b) c", "А (б) в"),),
    ),
    Rule(
        id="glued_markup",
        title=QT_TRANSLATE_NOOP("QaRules", "Missing space before a substitution"),
        category="russian", locale="ru",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Missing space before a substitution — the words will "
                       "stick together"),
        params={"min_word_len": 3, "ending_wrappers": ["Select_CString"],
                "ending_suffixes": ["_END"], "ending_calls": [],
                "allow_inside_word": False},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "A word of 3+ letters: one or two letters get a pronoun "
                       "attached on purpose — «к н[X.GetHerHis]» yields «к нему»"),
        example_bad=(("House [GetPlayer.GetDynasty.GetName]",
                      "дома[GetPlayer.GetDynasty.GetName]"),),
        example_ok=(("House [GetPlayer.GetDynasty.GetName]",
                     "дома [GetPlayer.GetDynasty.GetName]"),),
    ),
    Rule(
        id="linking_calque",
        title=QT_TRANSLATE_NOOP("QaRules", "Calque of an English copula"),
        category="russian", locale="ru",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "A substitution after a copula verb: «склонны быть "
                       "Верность». An appositive turn is needed — «склонны "
                       "проявлять черту: …»"),
        params={"verbs": list(CALQUE_VERBS)},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "CK3 names traits with nouns («Верность», «Отвага»), so "
                       "«склонны быть [Trait]» unfolds into nonsense"),
        example_bad=(("Beesburys tend to be [GetTrait('loyal').GetName( X )]",
                      "Бисбери склонны быть [GetTrait('loyal').GetName( X )]"),),
        example_ok=(("Beesburys tend to be [GetTrait('loyal').GetName( X )]",
                     "Бисбери склонны проявлять черту: [GetTrait('loyal').GetName( X )]"),),
    ),
    Rule(
        id="inconsistent",
        title=QT_TRANSLATE_NOOP("QaRules", "Same original translated differently"),
        category="consistency",
        message=QT_TRANSLATE_NOOP(
            "QaRules", "The same original is translated differently in the project"),
        params={"min_length": 0},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "Not an error but a reason to check: one English word can "
                       "be different things in different places"),
    ),
    Rule(
        id="len_ratio", title=QT_TRANSLATE_NOOP("QaRules", "Suspicious length"),
        category="length", enabled=False,
        message=QT_TRANSLATE_NOOP(
            "QaRules", "Suspicious length of the translation"),
        params={"min_ratio": 0.5, "max_ratio": 2.0, "min_source_len": 10},
        note=QT_TRANSLATE_NOOP(
            "QaRules", "A heuristic: noisier than it is useful, hence off"),
        example_bad=(("A reasonably long English sentence here", "Коротко"),),
        example_ok=(("A reasonably long English sentence here",
                     "Достаточно длинное предложение по-русски вот"),),
    ),
)

BY_ID: dict[str, Rule] = {r.id: r for r in BUILTIN_RULES}


class RuleSet:
    """Готовый к применению набор правил."""

    def __init__(self, rules):
        self.rules: tuple[Rule, ...] = tuple(rules)
        self.by_id: dict[str, Rule] = {r.id: r for r in self.rules}
        # Своё правило, съевшее на одной строке больше SLOW_RULE_SECONDS,
        # выключается до конца прохода. Копится здесь, а не в глобальной
        # переменной: набор живёт ровно один проход, и следующий начинается
        # с чистого листа — правило могло споткнуться об одну строку из ста
        # тысяч, и наказывать его навсегда не за что.
        self.exhausted: set[str] = set()
        self.spent: dict[str, float] = {}

    # --- доступ ---

    def __iter__(self):
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    def get(self, code: str) -> Rule | None:
        return self.by_id.get(code)

    def active(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.enabled)

    def active_ids(self) -> set[str]:
        return {r.id for r in self.active()}

    def severity(self, code: str) -> str:
        rule = self.by_id.get(code)
        return rule.severity if rule else WARNING

    def message(self, code: str) -> str:
        rule = self.by_id.get(code)
        return rule.message_text() if rule else code

    def codes(self) -> dict[str, tuple[str, str]]:
        """Совместимый с прежним qa.CODES словарь."""
        return {r.id: (r.severity, self.message(r.id)) for r in self.rules}

    def restricted_to(self, codes) -> RuleSet:
        """Только перечисленные правила — и они включены, каким бы ни был дефолт."""
        wanted = set(codes)
        return RuleSet(replace(r, enabled=r.id in wanted) for r in self.rules)

    def with_rule(self, rule: Rule) -> RuleSet:
        return RuleSet(rule if r.id == rule.id else r for r in self.rules)

    # --- применение ---

    def check(self, en_text: str, ru_text: str) -> list[str]:
        """Коды замечаний для пары «оригинал — перевод».

        Правило, съевшее слишком много времени, гаснет до конца прохода — см.
        `SLOW_RULE_SECONDS` и `exhausted`.
        """
        found: list[str] = []
        for rule in self.rules:
            if not rule.enabled or rule.id in PROJECT_WIDE:
                continue
            if rule.id in self.exhausted:
                continue
            if rule.id == EMPTY:
                # Пустой перевод обрывает разбор: остальные замечания к пустой
                # строке отношения не имеют и только затопили бы список.
                if not ru_text.strip():
                    return [EMPTY]
                continue
            check = check_of(rule)
            if check is None:
                continue
            started = time.perf_counter()
            try:
                hit = check(en_text, ru_text, rule.params)
            except Exception:   # noqa: BLE001 — правило с битой настройкой гасим
                # Настройку правят руками: `qa_rules.json` носят между машинами,
                # `.pdxqa` пересылают друг другу — ради этого файлы и заведены.
                # Опечатка в числе (`min_word_len: "три"`) добирается до `int()`
                # уже внутри проверки, а идёт она по сотне тысяч строк, и падать
                # посреди прохода из-за одного правила нельзя. Гасим его, как
                # уже гасим правило с неразбираемым выражением (`_user_re`);
                # разбираться с настройкой — работа окна правил.
                continue
            spent = time.perf_counter() - started
            self.spent[rule.id] = self.spent.get(rule.id, 0.0) + spent
            if rule.origin == USER and spent >= SLOW_RULE_SECONDS:
                self.exhausted.add(rule.id)
            if hit:
                found.append(rule.id)
        if not ru_text.strip():
            return []           # пусто, но правило про пустоту выключено
        return found


def default_ruleset() -> RuleSet:
    return RuleSet(BUILTIN_RULES)


# --- пресеты -------------------------------------------------------------
#
# Пресет — такая же дельта, как пользовательская правка, только готовая. Числа
# в комментариях сняты на живом переводе agoot (136 113 переведённых строк).

CUSTOM = "custom"

PRESET_ORDER = ("strict", "ck3_ru", "hoi4_ru", "ck2_ru", "stellaris_ru",
                "quiet", CUSTOM)
PRESET_LABELS = {
    "strict": QT_TRANSLATE_NOOP("QaRules", "Strict"),
    "ck3_ru": QT_TRANSLATE_NOOP("QaRules", "CK3 · Russian (recommended)"),
    "hoi4_ru": QT_TRANSLATE_NOOP("QaRules", "HOI4 · Russian"),
    "ck2_ru": QT_TRANSLATE_NOOP("QaRules", "CK2 · Russian"),
    "stellaris_ru": QT_TRANSLATE_NOOP("QaRules", "Stellaris · Russian"),
    "quiet": QT_TRANSLATE_NOOP("QaRules", "Breakage only"),
    CUSTOM: QT_TRANSLATE_NOOP("QaRules", "Own"),
}
PRESET_NOTES = {
    "strict": QT_TRANSLATE_NOOP(
        "QaRules", "Every rule on, no leniency. For proofreading a finished "
                   "translation, when noise is tolerable but a miss is not."),
    "ck3_ru": QT_TRANSLATE_NOOP(
        "QaRules", "Techniques of the Russian CK3 translation are not counted "
                   "as errors: a wrapper for inflection, an added #L, formatting "
                   "flags. On a live translation (136 113 rows) — 37 040 issues "
                   "against 12 591."),
    "hoi4_ru": QT_TRANSLATE_NOOP(
        "QaRules", "The Russian HOI4 inflects with functions of its own — "
                   "[JAP.GetAdjRuLower] instead of [JAP.GetAdjective], an ending "
                   "glued to the word. On the vanilla translation (124 893 rows) "
                   "— 5 269 issues against 11 072."),
    "ck2_ru": QT_TRANSLATE_NOOP(
        "QaRules", "The Russian CK2 inflects everything: 259 functions of the "
                   "game do the endings, and the translator adds an address "
                   "where English has none. On the vanilla translation "
                   "(89 616 rows) — 24 047 issues against 45 593."),
    "stellaris_ru": QT_TRANSLATE_NOOP(
        "QaRules", "Stellaris inflects names with its own grammar system, and "
                   "half of the noise here is names that match the original. "
                   "On the vanilla translation (148 751 rows) — 29 525 issues "
                   "against 32 969, and 17 156 of them are lowered to a signal."),
    "quiet": QT_TRANSLATE_NOOP(
        "QaRules", "Only what breaks the text in the game: lost variables, icons "
                   "and references, unclosed tags, an empty translation."),
    CUSTOM: QT_TRANSLATE_NOOP(
        "QaRules", "Built-in values without a preset — tuned by hand from here."),
}

# Головы вызовов, которыми переводчик оборачивает подстановку ради склонения.
# Не опечатка, а штатный приём: 59% всех расхождений по скобкам — замена
# английской ссылки на такую обёртку.
GRAMMAR_WRAPPERS = ["Concept", "Select_CString"]

# Склоняющие функции русских переводов живут отдельно (`core/inflections.py`):
# это данные, снятые с живых деревьев, и место им рядом друг с другом, а не
# посреди описания правил. Здесь — только имена, которыми их зовут пресеты.
HOI4_RU_CALLS = inflections.HOI4_RU_CALLS
HOI4_RU_ENDINGS = inflections.HOI4_RU_ENDINGS
CK2_RU_CALLS = inflections.CK2_RU_CALLS

# Что остаётся включённым в «Только поломках»
_QUIET_KEEP = frozenset(
    {EMPTY, "dollar_mismatch", "icon_mismatch", "fmt_broken", "brackets_mismatch"})

PRESETS: dict[str, dict] = {
    CUSTOM: {},
    "strict": {
        "len_ratio": {"enabled": True},
        "inconsistent": {"severity": WARNING},
        "edge_space": {"params": {"compare_with_source": False}},
        "unbalanced_quotes": {"params": {"only_if_source_balanced": False}},
    },
    "ck3_ru": {
        # 33 703 → 26 001 (обёртки) → 13 582 (обёртка вместо ссылки) → 9 955
        # (флаги оформления вида |E не считаются расхождением)
        "brackets_mismatch": {"params": {
            "ignore_extra_heads": GRAMMAR_WRAPPERS,
            "allow_replacement": True,
            "ignore_flags": True,
        }},
        # 1 179 → 513: дописанный ради падежа #L — приём, а не потеря тега
        "fmt_mismatch": {"params": {"allow_extra_tags": ["#L"]}},
        # 380 → 345
        "double_space": {"params": {"ignore_if_in_source": True}},
        # не ошибка, а повод свериться — 11 449 строк с завышенной серьёзностью
        "inconsistent": {"severity": INFO},
    },
    "hoi4_ru": {
        # Замер на ванильном русском HOI4 (124 893 строки с переводом):
        # brackets_mismatch 5 028 → 746, glued_markup 1 249 → 5. Оставшееся —
        # кандидаты в настоящие ошибки, включая опечатки Paradox в именах
        # функций и потерянные пробелы («регионе[350.GetName],»).
        "brackets_mismatch": {"params": {
            "ignore_extra_tails": HOI4_RU_CALLS,
            "allow_replacement": True,
            "ignore_flags": True,
        }},
        "glued_markup": {"params": {
            "ending_calls": HOI4_RU_ENDINGS,
            "allow_inside_word": True,
        }},
        # Двойной пробел приезжает из самого оригинала — «£command_power  §Y…»
        # разделяет иконку и число именно так. 292 → 15.
        "double_space": {"params": {"ignore_if_in_source": True}},
        # Тот же довод, что и в ck3_ru: одинаковый оригинал, переведённый
        # по-разному, — повод свериться, а не ошибка.
        "inconsistent": {"severity": INFO},
    },
    "stellaris_ru": {
        # Замер на ванильной паре (148 751 строка с переводом): 32 969 → 29 525.
        # Главный источник шума здесь другой, чем у соседей: 17 156 строк, где
        # перевод совпал с оригиналом, — это термины и названия видов, планет и
        # модификаторов. Правило не выключаем (среди них прячется и настоящий
        # непереведённый текст), но криком оно быть перестаёт.
        "same_as_en": {"severity": INFO},
        # Русский переводчик Stellaris дописывает ссылки и подстановки в
        # варианты для падежей, поэтому «появилось в переводе» здесь норма;
        # потерянное правила по-прежнему ловят.
        "brackets_mismatch": {"params": {"allow_extra": True}},
        "dollar_mismatch": {"params": {"allow_extra": True}},
        "inconsistent": {"severity": INFO},
    },
    "ck2_ru": {
        # Замер на ванильной паре (89 616 строк с переводом): всего 45 593 →
        # 24 047, brackets_mismatch 21 905 → 9 924, glued_markup 13 101 → 3 546.
        # `allow_extra` — здесь не роскошь: русский переводчик CK2 постоянно
        # дописывает обращение там, где по-английски его нет («Ты славно
        # сража[X.GetLasLsya], [X.GetFirstName]»), и добавленная подстановка
        # игру не ломает. Потерянная — ломает, и её правило по-прежнему ловит.
        "brackets_mismatch": {"params": {
            "ignore_extra_tails": CK2_RU_CALLS,
            "allow_replacement": True,
            "allow_extra": True,
            "ignore_flags": True,
        }},
        "glued_markup": {"params": {
            "ending_calls": CK2_RU_CALLS,
            "allow_inside_word": True,
        }},
        "double_space": {"params": {"ignore_if_in_source": True}},
        "inconsistent": {"severity": INFO},
    },
    "quiet": {
        **{r.id: {"enabled": False} for r in BUILTIN_RULES if r.id not in _QUIET_KEEP},
        "brackets_mismatch": {"params": {
            "ignore_extra_heads": GRAMMAR_WRAPPERS,
            "allow_replacement": True,
            "ignore_flags": True,
        }},
    },
}


# --- оверлеи: дельта поверх набора --------------------------------------

OVERLAY_VERSION = 1


def _rule_with_delta(rule: Rule, delta: Mapping) -> Rule:
    """Правило с применённой дельтой. Неизвестное в дельте молча пропускается.

    Пропускаем намеренно: оверлей писала прошлая версия приложения, и параметр
    мог с тех пор исчезнуть. Падать из-за настройки, которой больше нет,
    приложение не должно — а незнакомый ключ, попав в `params`, сделал бы
    правило неотличимым от изменённого и навсегда осел бы в дельте.
    """
    changes: dict = {}
    if "enabled" in delta:
        changes["enabled"] = bool(delta["enabled"])
    if delta.get("severity") in SEVERITIES:
        changes["severity"] = delta["severity"]
    params = delta.get("params")
    if isinstance(params, Mapping):
        known = {k: v for k, v in params.items() if k in rule.params}
        if known:
            changes["params"] = {**rule.params, **known}
    return replace(rule, **changes) if changes else rule


def apply_delta(rules: RuleSet, delta: Mapping | None) -> RuleSet:
    """Набор с применённой дельтой `{id правила: {enabled/severity/params}}`."""
    if not delta:
        return rules
    return RuleSet(
        _rule_with_delta(r, delta[r.id])
        if isinstance(delta.get(r.id), Mapping) else r
        for r in rules
    )


def preset_of(overlay: Mapping | None) -> str:
    """Пресет оверлея; `custom` — если не задан или незнаком."""
    name = (overlay or {}).get("preset")
    return name if name in PRESETS else CUSTOM


def for_locale(rules: RuleSet, locale: str) -> RuleSet:
    """Выключить правила чужого языка перевода.

    Выключаем, а не выбрасываем: правило остаётся видимым в окне настройки —
    там понятно, почему оно молчит, — и включить его вручную по-прежнему можно.
    Выброшенное же правило выглядело бы как пропавшее без объяснений.

    Пустая локаль не выключает ничего: язык неизвестен, и молчать наугад
    хуже, чем показать лишнее.
    """
    if not locale:
        return rules
    return RuleSet(
        replace(r, enabled=False) if r.locale and r.locale != locale else r
        for r in rules)


def with_user_rules(rules: RuleSet, incoming) -> RuleSet:
    """Добавить свои правила к набору; одноимённое заменяется целиком.

    Замена, а не слияние: правило верхнего слоя написано пользователем целиком,
    и «унаследовать половину параметров» тут значило бы получить набор, который
    он не собирал.
    """
    incoming = tuple(incoming)
    if not incoming:
        return rules
    by_id = {r.id: r for r in incoming}
    kept = tuple(by_id.pop(r.id, r) for r in rules)
    return RuleSet(kept + tuple(r for r in incoming if r.id in by_id))


def resolve(*overlays: Mapping | None, locale: str = "") -> RuleSet:
    """Действующий набор: встроенные значения, язык перевода, затем слои.

    Язык — часть **основания**, а не последний штрих: иначе он затирал бы
    осознанный выбор пользователя. Включив «пропущен пробел перед
    подстановкой» вручную во французском проекте, он должен его получить —
    правило написано под русский, но переводчику виднее.

    Свои правила слоя приезжают до его дельты: дельта вправе их подправить, а
    вот заменить своё правило нижнего слоя целиком может только верхний слой,
    и делает он это своей записью в `custom`.
    """
    rules = for_locale(default_ruleset(), locale)
    for overlay in overlays:
        if not overlay:
            continue
        rules = apply_delta(rules, PRESETS.get(preset_of(overlay)))
        rules = with_user_rules(
            rules, for_locale(RuleSet(user_rules(overlay)), locale))
        rules = apply_delta(rules, overlay.get("rules"))
    return rules


def rule_delta(base: Rule, current: Rule) -> dict:
    """Чем `current` отличается от `base`. Пусто — правило не трогали."""
    delta: dict = {}
    if current.enabled != base.enabled:
        delta["enabled"] = current.enabled
    if current.severity != base.severity:
        delta["severity"] = current.severity
    params = {k: v for k, v in current.params.items() if base.params.get(k) != v}
    if params:
        delta["params"] = params
    return delta


def delta_between(base: RuleSet, current: RuleSet) -> dict:
    return {
        rule.id: delta
        for rule in current
        if (known := base.get(rule.id)) is not None
        and (delta := rule_delta(known, rule))
    }


def make_overlay(preset: str, rules: RuleSet, *,
                 under: Mapping | None = None, locale: str = "") -> dict:
    """Оверлей, который вместе с `under` даёт ровно `rules`.

    `under` — слой, лежащий ниже (для проектного оверлея это глобальный):
    иначе проект записал бы себе копию глобальных правок и перестал бы за ними
    следовать. По той же причине в `custom` попадают только правила, которых
    внизу нет: правило, заведённое на все проекты, остаётся жить там, а правка
    его в проекте уходит в дельту.

    `locale` — язык перевода, на котором собран `rules`. Он тоже должен войти в
    основание, а не в дельту: иначе француз записал бы себе «выключить правила
    русской грамматики», и они остались бы выключенными после смены языка
    проекта — без всякого следа о том, кто их выключил.
    """
    base = resolve(under, {"preset": preset}, locale=locale)
    overlay = {
        "version": OVERLAY_VERSION,
        "preset": preset if preset != CUSTOM else None,
        "rules": delta_between(base, rules),
    }
    own = [dump_user_rule(r) for r in rules
           if r.origin == USER and base.get(r.id) is None]
    if own:
        overlay["custom"] = own
    return overlay


def is_empty_overlay(overlay: Mapping | None) -> bool:
    """Ничего не настроено — такой оверлей можно не хранить вовсе."""
    overlay = overlay or {}
    return (preset_of(overlay) == CUSTOM
            and not overlay.get("rules") and not user_rules(overlay))

"""Реестр разметки Paradox: единственное описание токенов на всё приложение.

До этого модуля описание жило в `core/qa.py`, и оттуда регулярки импортировали
пятеро: подсветка полей, экранирование при машинном переводе, классификация
правок оригинала, поиск похожих строк и авто-игнор при сканировании. Добавить
токен означало пройтись по всем пятерым и нигде не забыть — а забыть легко,
потому что каждый берёт свой поднабор и в своём порядке.

Здесь у каждого токена сказано, кто его использует и как:

* `color`      — имя цвета в `theme.py`; None значит «не подсвечивается»;
* `shield`     — прятать от машинного перевода (`core/mt.py`);
* `strip_with` — чем заменять при вычистке разметки; None значит «не трогать»;
* `structural` — участвует в решении «правка смысловая или косметическая»
                 (`core/textdiff.py`), а значит влияет на статус «Устарело».

**Порядок (`order`) значим в трёх местах.** При экранировании закрывающий
`#!` обязан искаться раньше открывающих тегов, иначе он останется голым в
тексте, уехавшем в переводчик. Тег с параметром (`#TOOLTIP:KEY`) обязан
искаться раньше простого `#tag`, иначе хвост после двоеточия уходит
переводчику как обычный текст и тултип ломается. При подсветке позднее
правило перекрывает раннее на пересекающихся кусках.

**Токены не одной игры.** Поле `game` говорит, чья это разметка: `§Y…§!` и
`£icon` — HOI4/EU4/Stellaris, `@name!` и `#bold` — CK3. Ищутся все и всегда:
формат у серии общий, мод к HOI4 переводят тем же окном, что и мод к CK3, а
цена лишнего токена — ноль совпадений на чужих данных: ни `§`, ни `£` не
встретились ни разу на 289 940 строках баз CK3 (ваниль плюс AGOT).

**Токен внутри токена решается порядком, а не вложенной регуляркой.** У HOI4
таких сочетаний три, и каждое разбирается тем, кто идёт первым: `§[GetColour]`
— цветом (`color_script`, до скобки), `[Select_CString(…'§Y'…)]` — скобкой
(простой `§Y` ищется после неё), `£command_power£$COST$` — иконкой, а не
«иконкой из переменной». Проверено на всём ванильном дереве HOI4: после
`strip_markup` не остаётся ни одного `§` или `£`, и ни один из них не доезжает
до машинного переводчика (129 087 строк).

**И отдельно: `@name!` ищется после `[…]`.** `shield_tags` собирает
непересекающиеся диапазоны в порядке токенов и отбрасывает всякий позднейший,
который с чем-то пересёкся. Пойди иконка первой — она забрала бы `@gold!`
внутри `[Select_CString(x,'@gold!','')]`, диапазон всей скобки был бы отброшен
как пересекающийся, и весь скриптовый вызов уехал бы в переводчик сырым. На
живых данных таких строк 12 в ванили и 18 в моде, то есть это не гипотеза.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CK3 = "ck3"
OTHER = "other"      # токен другой игры серии — в CK3 не встречается


@dataclass(frozen=True, slots=True)
class Token:
    id: str
    title: str
    pattern: re.Pattern
    order: int
    color: str | None = None
    bold: bool = False
    shield: bool = False
    strip_with: str | None = None
    structural: bool = False
    game: str = CK3
    note: str = ""


TOKENS: tuple[Token, ...] = (
    Token(
        id="color_script",
        title="Colour from a script call §[…]",
        pattern=re.compile(r"§\[[^\[\]]*\]"),
        # Раньше `bracket` — иначе скобка забирает свой кусок первой, а от цвета
        # остаётся голая §, и она съедает первую букву следующего слова:
        # `§[GetColour]red` превращался в `ed`. Простой `§Y`, наоборот, ищется
        # ПОСЛЕ скобки (`color_open`, порядок 24) — иначе цвет внутри
        # скриптового вызова украл бы диапазон у всего вызова, как это было с
        # иконкой `@gold!`. Вложенных скобок формат не знает, поэтому оба
        # правила уживаются. 13 строк ванильной HOI4.
        order=4,
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
    ),
    Token(
        id="bracket",
        title="Script reference [ ]",
        pattern=re.compile(r"\[[^\[\]]*\]"),
        order=10,
        color="markup.bracket",
        shield=True,
        strip_with="",
        structural=True,
        note="[GetTrait('x').GetName], [men_at_arms|E] — nesting is not supported",
    ),
    Token(
        id="icon_pound",
        title="Icon £ £",
        pattern=re.compile(r"£[A-Za-z0-9_]+(?:\|[A-Za-z0-9]+)?£?"),
        order=12,          # раньше icon_var и dollar — см. примечание у icon_var
        color="markup.icon",
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
        note="An EU4/HOI4/Stellaris token. Never seen in CK3: 0 matches "
             "over 151 815 mod rows and 244 118 vanilla database entries. "
             "The closing £ is optional: vanilla HOI4 pairs it 178 times "
             "against 1 643 bare £command_power. The flag after | is the icon "
             "size (£operative_mission_icons_small|8£) and belongs to the "
             "token, exactly like the flags of $VALUE|=+0$",
    ),
    Token(
        id="icon_var",
        title="Icon named by a variable £$…$£",
        pattern=re.compile(r"£\$[^$]*\$£?"),
        # После `bracket` и `icon_pound`, но до `dollar`. До `dollar` — потому
        # что переменная внутри это имя иконки, а не подстановка в текст, и
        # уезжать в переводчик она должна вместе с иконкой. После `icon_pound`
        # — из-за `£command_power£$COST|H0$`: там вторая £ закрывает первую
        # иконку, и начни разбор отсюда, эта пара распалась бы надвое.
        # 29 строк ванильной HOI4.
        order=14,
        color="markup.icon",
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
    ),
    Token(
        id="dollar",
        title="Variable $ $",
        pattern=re.compile(r"\$[A-Za-z0-9_.|=+\-]+\$"),
        order=20,
        color="markup.dollar",
        shield=True,
        strip_with="",
        structural=True,
        note="$VALUE$, $VALUE|=+0$ — flags after | belong to the token",
    ),
    Token(
        id="color_close",
        title="Colour close §!",
        pattern=re.compile(r"§!"),
        # Закрывающий раньше открывающего — по тому же правилу, что у `#!`.
        # Пересечения здесь нет (после § стоит «!», а не буква), но порядок
        # держим единым: иначе правило пришлось бы вспоминать заново на каждом
        # новом парном токене.
        order=22,
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
        note="The HOI4/EU4/Stellaris colour code. 11 294 rows of vanilla HOI4 "
             "close a colour, 19 773 closings in all",
    ),
    Token(
        id="color_open",
        title="Colour §X",
        pattern=re.compile(r"§[A-Za-z0-9]"),
        order=24,
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
        note="§Y, §R, §G — one character of colour code. 11 290 rows of "
             "vanilla HOI4, 19 761 openings. Never seen in CK3, where the same "
             "job is done by #bold and its kin",
    ),
    Token(
        id="grammar_variant",
        title="Grammar variant |||tag:",
        pattern=re.compile(r"\|\|\|[A-Za-z0-9_,]*:?"),
        # После скобки: вариант живёт и внутри скриптового вызова —
        # `[leader.GetAXX::вернулся|||fem:вернулась]`, — и там диапазон должен
        # достаться вызову целиком, ровно как цвету внутри Select_CString.
        order=26,
        color="markup.format",
        bold=True,
        shield=True,
        # пробелом, а не пустотой: по разные стороны разделителя стоят два
        # варианта одного слова, и «энергия|||gen:энергии» без него слипается
        # в «энергияэнергии» — поиск похожих строк такого не прощает
        strip_with=" ",
        structural=True,
        game=OTHER,
        note="Stellaris 3.6 and later: «A $1$|||vowel:An $1$» — the game picks "
             "the variant by the tags of the name. Written by the translator, "
             "not by the author: 6 327 rows in the Russian tree against 463 in "
             "the English one",
    ),
    Token(
        id="grammar_tags",
        title="Grammar tags &!",
        pattern=re.compile(r"&![A-Za-z0-9_,]*"),
        order=28,
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        game=OTHER,
        note="Stellaris: «Empress&!fem,vowel» — gender, number, «starts with a "
             "vowel»; «&!0» stops the tags of a sub-name from being forwarded. "
             "2 278 rows of the Russian tree carry them",
    ),
    Token(
        id="icon_at",
        title="Icon @name!",
        pattern=re.compile(r"@[A-Za-z0-9_]+!"),
        order=35,          # обязательно после bracket — см. шапку модуля
        color="markup.icon",
        shield=True,
        strip_with="",
        structural=True,
        note="The real CK3 icon: @gold!, @warning_icon!. 3 138 vanilla rows, "
             "3 505 in a live mod. Dynamic names (@aptitude:4:inherit_color!, "
             "@[X.GetIconKey]_icon!) are 1% and stay uncovered: their innards "
             "are already shielded by bracket and dollar",
    ),
    Token(
        id="fmt_close",
        title="Formatting close #!",
        pattern=re.compile(r"#!"),
        order=40,          # раньше fmt_open — см. шапку модуля
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
    ),
    Token(
        id="fmt_param",
        title="Formatting tag with a parameter #tag:…",
        pattern=re.compile(
            r"#(?!!)[A-Za-z][A-Za-z_;]*:"
            r"(?:\{[^{}\[\]]*\}"
            r"|[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*(?:,[A-Za-z0-9_\-]*)*)"
            r"(?:;[A-Za-z][A-Za-z_]*)*"),
        order=45,          # раньше fmt_open — см. шапку модуля
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        note="#TOOLTIP:KEY, #TOOLTIP:CHARACTER,[…], #indent_newline:2, "
             "#font:TitleFont, #size:15, #color:{0.8,0.7,0.5};bold. "
             "331 rows across vanilla and a live mod. Deliberately NOT covered: "
             "#color:{[ToTextFormatColor(…)]} — the bracket owns that span",
    ),
    Token(
        id="fmt_open",
        title="Formatting tag #…",
        pattern=re.compile(r"#(?!!)[A-Za-z][A-Za-z_;]*"),
        order=50,
        color="markup.format",
        bold=True,
        shield=True,
        strip_with="",
        structural=True,
        note="#bold, #weak, #high;italic — the list is open and case-insensitive",
    ),
    Token(
        id="newline",
        title="Line break \\n",
        pattern=re.compile(r"\\n"),
        order=60,
        shield=True,
        strip_with=" ",    # пробелом, иначе слова по краям переноса слипнутся
        note="The two-character Paradox break, not a real \\n",
    ),
    Token(
        id="escape",
        title="Escaped character",
        pattern=re.compile(r'\\n|\\"'),
        order=70,
        color="markup.escape",
        bold=True,
        note="Highlighting only: covers \\n and \\\" with one rule",
    ),
)

BY_ID: dict[str, Token] = {t.id: t for t in TOKENS}


def _ordered(tokens) -> tuple[Token, ...]:
    return tuple(sorted(tokens, key=lambda t: t.order))


def shield_tokens() -> tuple[Token, ...]:
    """Токены, которые прячутся от машинного перевода — в порядке поиска."""
    return _ordered(t for t in TOKENS if t.shield)


def structural_patterns() -> tuple[re.Pattern, ...]:
    """Разметка, изменение которой переводчик обязан перенести."""
    return tuple(t.pattern for t in _ordered(t for t in TOKENS if t.structural))


def highlight_rules() -> tuple[tuple[re.Pattern, str, bool], ...]:
    """(шаблон, имя цвета, жирный) — в порядке наложения."""
    return tuple((t.pattern, t.color, t.bold)
                 for t in _ordered(t for t in TOKENS if t.color))


def strip_tokens() -> tuple[Token, ...]:
    """Токены, которые не являются прозой, — в порядке поиска.

    Ровно те, что убирает `strip_markup`. Отдельным списком нужны там, где
    разметку надо не убрать, а обойти: подсветка терминов ищет слова в живом
    тексте и не должна подчёркивать нутро `[GetTrait…]`.
    """
    return _ordered(t for t in TOKENS if t.strip_with is not None)


def spans(text: str, tokens: tuple[Token, ...]) -> list[tuple[int, int]]:
    """Непересекающиеся куски разметки, отсортированные по началу.

    Порядок токенов значим — он и решает, кто заберёт спорный кусок: диапазон
    берётся, только если не пересекается с уже взятым, поэтому `@gold!` внутри
    `[Select_CString(x,'@gold!','')]` не отрывает кусок у всей скобки (разбор —
    в шапке модуля). Раньше этот проход жил внутри `mt.shield_tags`; вторая
    копия в подсветке терминов разъехалась бы с первой на первом же новом
    токене.
    """
    found: list[tuple[int, int]] = []
    for token in tokens:
        for m in token.pattern.finditer(text):
            if not any(s <= m.start() < e or s < m.end() <= e for s, e in found):
                found.append((m.start(), m.end()))
    found.sort()
    return found


def strip_markup(text: str) -> str:
    """Убрать разметку, оставив только переводимый текст.

    Нужна там, где разметка мешает мерить: сравнение длин, поиск похожих строк
    и вопрос «а есть ли тут что переводить вообще».
    """
    for token in strip_tokens():
        text = token.pattern.sub(token.strip_with, text)
    return text.strip()


def pattern(token_id: str) -> re.Pattern:
    return BY_ID[token_id].pattern

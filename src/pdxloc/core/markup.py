"""The Paradox markup registry: one description of the tokens for the whole app.

Before this module the description lived in `core/qa.py`, and five callers
imported the regexes from there: the field highlighting, the shielding for machine
translation, the classification of edits to the original, the similar-rows search
and the auto-ignore during a scan. Adding a token meant walking all five and
forgetting none — and forgetting is easy, because each of them takes its own
subset in its own order.

Here every token says who uses it and how:

* `color`      — the colour name in `theme.py`; None means «not highlighted»;
* `shield`     — hide it from machine translation (`core/mt.py`);
* `strip_with` — what to replace it with when stripping markup; None means «leave
                 it alone»;
* `structural` — takes part in deciding «meaningful edit or cosmetic»
                 (`core/textdiff.py`), and therefore affects the «Outdated»
                 status.

**The `order` matters in three places.** When shielding, the closing `#!` must be
searched for before the opening tags, or it is left bare in the text that goes to
the translator. A tag with a parameter (`#TOOLTIP:KEY`) must be searched for
before a plain `#tag`, or the tail after the colon goes to the translator as
ordinary text and the tooltip breaks. When highlighting, a later rule overrides an
earlier one where the two overlap.

**The tokens are not all from one game.** The `game` field says whose markup it
is: `§Y…§!` and `£icon` belong to HOI4, EU4 and Stellaris, `@name!` and `#bold` to
CK3. All of them are searched for, always: the format is shared across the series,
a HOI4 mod is translated in the same window as a CK3 one, and the price of a
superfluous token is zero matches on foreign data — neither `§` nor `£` occurred
even once across 289 940 rows of the CK3 databases (vanilla plus AGOT).

**A token inside a token is settled by order, not by a nested regex.** HOI4 has
three such combinations, and each is taken by whoever comes first: `§[GetColour]`
by the colour (`color_script`, ahead of the bracket), `[Select_CString(…'§Y'…)]`
by the bracket (a plain `§Y` is searched for after it), `£command_power£$COST$` by
the icon rather than by «an icon out of a variable». Checked over the whole
vanilla HOI4 tree: after `strip_markup` not a single `§` or `£` is left, and none
of them reaches the machine translator (129 087 rows).

**And separately: `@name!` is searched for after `[…]`.** `shield_tags` collects
non-overlapping ranges in token order and discards any later one that overlapped
something. Let the icon go first and it would take the `@gold!` inside
`[Select_CString(x,'@gold!','')]`, the range of the whole bracket would be
discarded as overlapping, and the entire scripted call would go to the translator
raw. On live data there are 12 such rows in the vanilla tree and 18 in the mod, so
this is not a hypothesis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CK3 = "ck3"
OTHER = "other"      # a token of another game in the series: never seen in CK3


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
        # The closing one before the opening one, by the same rule as `#!`.
        # There is no overlap here — a «!» follows the §, not a letter — but the order
        # is kept uniform: otherwise the rule would have to be recalled from scratch on
        # every new paired token.
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
        # After the bracket: a variant also lives inside a scripted call —
        # `[leader.GetAXX::вернулся|||fem:вернулась]` — and there the range must go to
        # the call whole, exactly as a colour does inside Select_CString.
        order=26,
        color="markup.format",
        bold=True,
        shield=True,
        # with a space rather than with nothing: on either side of the separator stand
        # two forms of one word, and «энергия|||gen:энергии» without it congeals into
        # «энергияэнергии» — the similar-rows search does not forgive that
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
        order=35,          # must come after bracket — see the module header
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
        order=40,          # before fmt_open — see the module header
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
        order=45,          # before fmt_open — see the module header
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
        strip_with=" ",    # with a space, or the words on either side of the break congeal
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
    """The tokens hidden from machine translation, in search order."""
    return _ordered(t for t in TOKENS if t.shield)


def structural_patterns() -> tuple[re.Pattern, ...]:
    """Markup whose change the translator must carry over."""
    return tuple(t.pattern for t in _ordered(t for t in TOKENS if t.structural))


def highlight_rules() -> tuple[tuple[re.Pattern, str, bool], ...]:
    """(pattern, colour name, bold), in the order they are laid on."""
    return tuple((t.pattern, t.color, t.bold)
                 for t in _ordered(t for t in TOKENS if t.color))


def strip_tokens() -> tuple[Token, ...]:
    """The tokens that are not prose, in search order.

    Exactly the ones `strip_markup` removes. A separate list is needed where the
    markup has to be stepped around rather than removed: the term highlighting
    looks for words in the living text and must not underline the innards of
    `[GetTrait…]`.
    """
    return _ordered(t for t in TOKENS if t.strip_with is not None)


def spans(text: str, tokens: tuple[Token, ...]) -> list[tuple[int, int]]:
    """Non-overlapping pieces of markup, sorted by their start.

    The order of the tokens matters — it is what decides who takes a disputed
    piece: a range is taken only when it does not overlap one already taken, so
    the `@gold!` inside `[Select_CString(x,'@gold!','')]` does not tear a piece
    off the whole bracket (the reasoning is in the module header). This pass used
    to live inside `mt.shield_tags`; a second copy in the term highlighting would
    have drifted from the first on the very next new token.
    """
    found: list[tuple[int, int]] = []
    for token in tokens:
        for m in token.pattern.finditer(text):
            if not any(s <= m.start() < e or s < m.end() <= e for s, e in found):
                found.append((m.start(), m.end()))
    found.sort()
    return found


def strip_markup(text: str) -> str:
    """Remove the markup, leaving only the translatable text.

    Needed where markup gets in the way of measuring: comparing lengths, the
    similar-rows search, and the question «is there anything to translate here at
    all».
    """
    for token in strip_tokens():
        text = token.pattern.sub(token.strip_with, text)
    return text.strip()


def pattern(token_id: str) -> re.Pattern:
    return BY_ID[token_id].pattern

"""The registry of check rules: what we check, how strictly, and with what leniency.

Why it was needed. Measurements on a live translation (136,113 rows) showed that
the check complains three times more often than there are errors: 18,527 remarks
about brackets, of which the real ones are ~20%, because the translator wraps a
substitution in `Concept(…)` for the sake of declension — a standard device, not
a typo. Fitting the translation to the check is the tail wagging the dog; the
right thing is to set the check up properly.

The arrangement is hybrid, and that is deliberate:

* **built-in rules** — functions with parameters. It is the parameters, and not
  "regexes of one's own", that remove the measured noise: nine tick boxes
  against tens of thousands of false hits;
* **user rules** — six declarative kinds (`KINDS`). A fully declarative language
  for the built-in ones would have been self-deception: on "a space is missing
  before the substitution" and "the same source is translated differently" it
  would have degenerated into a field where one writes the name of a Python
  function.

Both live in one set with the same schema, are switched on the same way and are
shown the same way. The user is not supposed to see the border.

The default parameter values reproduced the behaviour from before the registry.
Two of them have been changed since — `edge_space.compare_with_source` and
`unbalanced_quotes.only_if_source_balanced`: the measurement showed that 93% and
74% of the hits fell on a space and a quote standing in the source itself. Both
defaults only quiet hits down and add not a single one (checked by
`test_qa_defaults.py`), so the change is safe.

**Overlays** lie on top of the set — deltas, not full dumps. There are two
layers, the global one and the project one; the order of application is:
built-in values → the preset and the edits of the global layer → the preset and
the edits of the project. The delta matters: a full dump would freeze the set at
the version of the application it was saved in, and new rules with mended
defaults would never reach the user.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from collections.abc import Callable, Mapping

from pdxloc.core import games, inflections, markup
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITIES = (ERROR, WARNING, INFO)
SEVERITY_RANK = {ERROR: 0, WARNING: 1, INFO: 2}

BUILTIN = "builtin"

# How much time a rule of one's own is entitled to spend on ONE row before it is
# put out for the rest of the pass.
#
# The reason is catastrophic backtracking: `(\w+)+$` on a long row is computed
# for minutes, while a pass goes over a hundred thousand rows. Half a second per
# row is already three orders of magnitude more than any honest rule takes, so
# there is nowhere for false hits to come from.
#
# **What this does not give, and promising otherwise would be untrue.** A single
# hung `re` call cannot be interrupted this way: the module has no timeout,
# signals do not work on Windows, and an outside engine would break the
# principle of a single dependency. The protection here is against "a rule
# spoiled the whole pass", not against "a rule hung the application". The second
# is caught earlier — `regex_warning` warns in the rules window before the run.
SLOW_RULE_SECONDS = 0.5

# Categories — the order sets the order of the groups in the rules window
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
    # The target language the rule belongs to. Empty means any. Set up for the
    # sake of `glued_markup` and `linking_calque`: both are about Russian
    # grammar, and a translator into French would get remarks about declension
    # for nothing.
    locale: str = ""
    # The examples work as a self-check: both in the rules window and in pytest.
    # The device is borrowed from LanguageTool, where every rule is obliged to
    # carry an example.
    example_ok: tuple[tuple[str, str], ...] = ()      # (source, translation) — quiet
    example_bad: tuple[tuple[str, str], ...] = ()     # (source, translation) — fires
    origin: str = BUILTIN

    def with_params(self, **changes) -> Rule:
        return replace(self, params={**self.params, **changes})

    # The labels are translated here and not in the rules window: both the F6
    # report and the hint of the «!» column come for them, and they would
    # diverge instantly. The text of a rule of one's own is not translated at
    # all: the user wrote it, and a coincidence with an English interface string
    # would replace it with somebody else's translation.
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


# --- helpers -------------------------------------------------------------

RE_ESCAPE_SEQ = re.compile(r"\\[nrt]")
# An insert glued to a whole word: «дома[GetPlayer…]» → in the game «домаСтарк»
RE_GLUED_TAIL = r"\[[^\[\]]*\]"
# The head of a call inside the bracket: [Concept('faith','вера')|E] → Concept
RE_HEAD = re.compile(r"^\[\s*([A-Za-z_][A-Za-z0-9_]*)")
# The same name without the bracket on the left — `tail_of` parses the last link
RE_HEAD_BARE = re.compile(r"^[?]?([A-Za-z_][A-Za-z0-9_]*)")
# Presentation flags at the end of a token: [men_at_arms|E] → [men_at_arms]
RE_TOKEN_FLAGS = re.compile(r"\|[^\[\]|]*(?=\]$)")

DEFAULT_PAIRS = (("«", "»"), ("(", ")"), ("[", "]"), ("{", "}"))


def _multiset(pattern: re.Pattern, text: str) -> Counter:
    return Counter(pattern.findall(text))


def head_of(token: str) -> str:
    """The name of the function inside the bracket — it tells a device from a typo."""
    match = RE_HEAD.match(token)
    return match.group(1) if match else ""


def tail_of(token: str) -> str:
    """The name of the called function — the last link of the chain in the bracket.

    `head_of` looks at the first word, and in CK3 that is the function
    (`[GetTrait('x').GetName]` → `GetTrait`). In HOI4 the scope comes first — a
    country tag or `ROOT`/`FROM` — and the function turns out to be at the end:
    `[JAP.GetAdjRuLower]`. The Russian localisation of HOI4 declines with exactly
    these tails, and without them the replacement `GetAdjective` →
    `GetAdjRuLower` cannot be told from a lost reference: 5,028 rows of the
    vanilla translation against 746 real divergences.
    """
    inner = token.strip("[]").split("|")[0]     # presentation flags do not count
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
    """Do the token sets diverge, with the leniencies taken into account."""
    if compare == "count":
        return sum(en_tokens.values()) != sum(ru_tokens.values())
    extra = ru_tokens - en_tokens          # appeared in the translation
    missing = en_tokens - ru_tokens        # lost in the translation

    if ignore_extra_heads or ignore_extra_tails:
        # A wrapper for the sake of grammar is not a divergence: the translator
        # added Concept(…)/Select_CString(…) to decline a term. In HOI4 the same
        # thing is done not by a wrapper but by a declining function at the end
        # of the chain ([JAP.GetAdjRuLower] instead of [JAP.GetAdjective]) —
        # hence the second list, the one by tails.
        forgiven = Counter({t: n for t, n in extra.items()
                            if head_of(t) in ignore_extra_heads
                            or tail_of(t) in ignore_extra_tails})
        extra -= forgiven
        if allow_replacement and forgiven and not extra:
            # The wrapper is not "on top of" but "instead of": the English
            # [CharAreIs(actor)] is replaced by [Select_CString(actor.IsFemale,
            # 'ведьма', 'колдун')], because Russian needs a gender. Measured on
            # a live translation: such cases are 59% of all bracket divergences,
            # more than pure wrappers. We quiet as many lost tokens as there are
            # wrappers added: a one-for-one replacement is forgiven, a real loss
            # is not.
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
        # A substitution that was not in the source does not break the game: it
        # is valid, there is simply more text. Russian needs this often — «Ты
        # славно сража[X.GetLasLsya], [X.GetFirstName].» where in English the
        # address is dropped. A lost substitution, on the contrary, leaves a hole
        # in the game, and this parameter does not touch it.
        extra = Counter()

    if compare == "set":
        return bool(set(extra) or set(missing))
    return bool(extra or missing)


@lru_cache(maxsize=64)
def _glue_re(min_word_len: int) -> re.Pattern:
    return re.compile(rf"[^\W\d_]{{{min_word_len},}}{RE_GLUED_TAIL}")


@lru_cache(maxsize=64)
def _calque_re(verbs: tuple[str, ...]) -> re.Pattern:
    """A linking word plus a substitution. The verbs are regex fragments, not plain words.

    The negation is cut off: «целью не может быть [Имя]» puts the substitution
    into the position of the subject, and the nominative case is right there.
    """
    return re.compile(r"(?<!не )\b(?:" + "|".join(verbs) + r")"
                      r"\s*\[(?:Get|[A-Z_]+\.Get)")


def _returns_word_ending(token: str, wrappers: tuple[str, ...],
                         suffixes: tuple[str, ...],
                         calls: tuple[str, ...] = ()) -> bool:
    """The substitution returns the ending of a word and not a name.

    To such ones it is written right up close, and that is the norm, not a lost
    space: `Select_CString(X.IsFemale, 'а', '')` turns «даровал» into
    «даровала», and the functions with the `_END` suffix
    (`GetAnimalType_RU_Acc_END`) were set up by translators for exactly the case
    endings.

    In HOI4 the same thing is done by the game itself, with separate functions:
    «объявил[CHI.GetVerbGendEndA_RU]» — 1,097 such joins in the vanilla Russian
    translation. We know them by the name of the call (`calls`), not by the
    argument.
    """
    if head_of(token) in wrappers:
        return True
    if tail_of(token) in calls:
        return True
    return any(f"{s}'" in token or f'{s}"' in token for s in suffixes)


def _glued_count(text: str, params: Mapping) -> int:
    text = RE_ESCAPE_SEQ.sub(" ", text)     # «\n» is not the letter n before a bracket
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
        # The substitution is not before the word but inside it:
        # «анти[X.GetAdjective]ое» — a prefix on the left, an ending on the
        # right, and there is nowhere for a space to come from. 279 joins in the
        # vanilla Russian HOI4 against 5 real lost spaces.
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


# --- the checks themselves -----------------------------------------------
#
# Each gets (source, translation, parameters) and answers "there is a remark".


def _check_dollar(en: str, ru: str, p: Mapping) -> bool:
    flags = bool(p.get("ignore_flags"))
    en_tokens = _tokens(markup.pattern("dollar"), en, ignore_flags=flags)
    ru_tokens = _tokens(markup.pattern("dollar"), ru, ignore_flags=flags)
    if p.get("only_if_all_lost"):
        # A measurement on a live translation parted two different cases: 789
        # rows where not a single variable was left in the translation (a hole
        # in the text right in the game), and 624 where the set simply differs —
        # there the translator most often moved or replaced a substitution
        # deliberately. The parameter quiets the second without touching the
        # first; off by default — a replacement happens to be an error too.
        return bool(en_tokens) and not ru_tokens
    return _differs(en_tokens, ru_tokens,
                    compare=p.get("compare", "multiset"), ignore_extra_heads=(),
                    allow_extra=bool(p.get("allow_extra")))


def _check_icon(en: str, ru: str, p: Mapping) -> bool:
    """The icons of both records — each kind on its own.

    Not as one common multiset: `£gold£` replaced by `@gold!` would come out
    equal in a common bag, whereas these are different tokens of different
    games, and swapping one for the other is exactly an error.
    """
    return any(_multiset(markup.pattern(token_id), en)
               != _multiset(markup.pattern(token_id), ru)
               for token_id in ("icon_pound", "icon_var", "icon_at"))


def _check_color(en: str, ru: str, p: Mapping) -> bool:
    """The colour codes of HOI4/EU4/Stellaris — each kind on its own.

    Separately, as with the icons: `§Y` (yellow) instead of `§R` (red) is not the
    same as "the colour is in place", and a closing `§!` without an opening one
    paints the rest of the row whole. `compare: count` leaves only the count, if
    the translator changes the shades deliberately.
    """
    compare = p.get("compare", "multiset")
    for token_id in ("color_open", "color_close", "color_script"):
        pattern = markup.pattern(token_id)
        if _differs(_multiset(pattern, en), _multiset(pattern, ru),
                    compare=compare, ignore_extra_heads=()):
            return True
    return False


def _check_grammar(en: str, ru: str, p: Mapping) -> bool:
    """Stellaris grammar: a tag or a variant lost in the translation.

    The comparison is one-sided, and that is not leniency but how the system is
    built: the variants for the cases are written by the **translator** (6,327
    rows of the Russian tree against 463 of the English), so what is added does
    not count as a divergence. A lost `&!fem`, on the other hand, changes the
    gender of a name in every phrase it gets substituted into — and noticing
    that in the game is only possible by chance.
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
        # The translator added #L for the sake of a case — a device, not a lost tag
        extra = Counter({t: n for t, n in extra.items() if t not in allowed})
    return bool(extra or (en_tags - ru_tags))


def _check_fmt_broken(en: str, ru: str, p: Mapping) -> bool:
    opens, closes = markup.pattern("fmt_open"), markup.pattern("fmt_close")
    # Only when the source is closed: in CK3 a #weak at the end of a row need not
    # be closed, and it is the mod itself that happens to be unbalanced.
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
    """A divergence in the number of tokens, tolerance and direction included.

    `delta` is how many tokens were lost: positive means "fewer in the
    translation". A function of its own, because the user kind `token_count`
    measures the very same thing.
    """
    tolerance = int(p.get("tolerance", 0))
    direction = p.get("direction", "any")
    if direction == "fewer":        # complain only about lost tokens
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
        # An edge space happens in the source too — that is how rows are glued in the game
        return (ru != ru.strip()) and (en == en.strip())
    return ru != ru.strip()


def _check_double_space(en: str, ru: str, p: Mapping) -> bool:
    pattern = markup.pattern("newline")
    # A paragraph break \n\n is not a double space: we count inside the pieces
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
        return False        # the source itself is unbalanced — the translation is not at fault
    return True


def _check_glued(en: str, ru: str, p: Mapping) -> bool:
    # We compare with the source: «[command_modifier_i|E]Minimum» is a lawful
    # join, and the translation is entitled to inherit it.
    return _glued_count(ru, p) > _glued_count(en, p)


def _check_calque(en: str, ru: str, p: Mapping) -> bool:
    # We do not compare with the source: in English "tend to be [Trait]" is
    # impeccable, it is only the Russian text that breaks.
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

# Checks that need not one row but the whole project
PROJECT_WIDE = ("inconsistent",)
# An empty translation is a special case: answering it with all the other
# remarks is pointless, so the check breaks off the parsing of the row
EMPTY = "empty_translated"

CALQUE_VERBS = (
    r"склонн\w+\s+быть", r"мог(?:ут|ла|ли)\s+быть",
    "бывают", "бывает", "рождаются", "рождается",
    "считаются", "считается", "слывут", "славятся",
)


# --- the kinds of user rules ---------------------------------------------
#
# Six kinds, and not a language for describing rules. The reason is the same one
# for which the built-in rules stayed functions: the real checks lean on parsing
# brackets, on the neighbouring rows of the project, on the markup registry —
# that cannot be expressed by a declaration, and an attempt would have
# degenerated into a field named "the name of a Python function".
#
# The kinds cover what a translator formulates for themselves: "these characters
# must not be in the translation", "as many such pieces in the translation as in
# the source", "after such a thing in the source the translation is obliged to
# hold this". Everything else is a reason to set up a built-in rule, not a line
# in a setting.

USER = "user"


@lru_cache(maxsize=256)
def _user_re(pattern: str, ignore_case: bool = False) -> re.Pattern | None:
    """The user's expression; `None` — it does not parse.

    A broken expression quiets its own rule and does not touch the rest: the
    check goes over a hundred thousand rows, and it has no right to fall over
    mid-pass because of an unclosed bracket in somebody else's setting. What
    exactly is wrong is shown by the rules window (`regex_error`) — that is
    where an error belongs, next to the input field.
    """
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error:
        return None


def regex_error(pattern: str) -> str:
    """The parser's complaint about the expression, or empty if all is well."""
    if not pattern:
        return ""
    try:
        re.compile(pattern)
    except re.error as e:
        return str(e)
    return ""


# A quantifier over a group that holds a quantifier inside it as well: `(\w+)+`,
# `(a*)*`, `(\d+\s?)+`. On a row that almost fits, the parser goes through
# exponentially many variants — seconds on a single row, while the check runs
# over a hundred thousand. The `re` module cannot be interrupted by anything: no
# timeout, no signal on Windows — so the only protection is to warn the human
# before they press F6.
_NESTED_QUANTIFIER = re.compile(r"\((?![?*+])[^()]*[*+][^()]*\)\s*[*+]")


def regex_warning(pattern: str) -> str:
    """A warning about an expression that may hang the check.

    Not an error: the expression parses and most likely works. But rules travel
    between translators in a `.pdxqa` file, and a rule received from outside is
    just as able to occupy the processor for a long time as one written by one's
    own hand.
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
    """The matches whole, not the groups.

    With brackets in the expression `findall` hands back the groups, and
    `(\\w+)` instead of `(?:\\w+)` would change the meaning of the rule
    silently. The user has no business knowing such a difference.
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
    """Found in the source — then we expect the matching thing in the translation.

    The device is taken from Okapi CheckMate (Patterns there): an expression over
    the source and a template for the answer, into which the groups are
    substituted (`\\1`). By default the template is looked for as text and not as
    an expression — otherwise the most obvious case would break silently:
    `$\\1$` in the role of an expression means "end of row, VALUE, end of row"
    and will match nothing.
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
            return False        # the template refers to a group that is not there
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
        # Identical halves («"» and «"») are counted for parity: equality of the
        # counters holds for them always and means nothing.
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
    """The kind of a user rule: what it is set up with and what it checks with."""

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
    """The checking function of a rule — its own for a built-in, shared for a kind."""
    if rule.kind == BUILTIN:
        return CHECKS.get(rule.id)
    kind = KINDS.get(rule.kind)
    return kind.check if kind is not None else None


def make_user_rule(rule_id: str, kind: str, *, title: str,
                   message: str = "", severity: str = WARNING,
                   category: str = "custom", enabled: bool = True,
                   params: Mapping | None = None, note: str = "",
                   locale: str = "") -> Rule:
    """A rule of one's own: the parameters of the kind plus what the user set.

    Unknown parameters are dropped right here — as in the overlay, so that a
    rule arrived from somebody else's version does not drag along a field that
    no longer exists.
    """
    spec = KINDS[kind]
    known = {k: v for k, v in (params or {}).items() if k in spec.defaults}
    return Rule(
        id=rule_id, title=title,
        # An unknown category would take the rule out of the window tree
        # entirely: the groups there are built from `CATEGORIES`, and a foreign
        # string would match none of them.
        category=category if category in CATEGORIES else "custom",
        message=message or title,
        severity=severity if severity in SEVERITIES else WARNING,
        enabled=enabled, kind=kind, params={**spec.defaults, **known},
        note=note, locale=locale, origin=USER,
    )


def dump_user_rule(rule: Rule) -> dict:
    """The record of a rule for the overlay and the exchange file — whole, not a delta.

    A delta is impossible here: a rule of one's own has no base to count it from.
    On the other hand "the new fields will arrive by themselves" is not needed
    here either — the fields are set by the user.
    """
    return {
        "id": rule.id, "kind": rule.kind, "title": rule.title,
        "message": rule.message, "category": rule.category,
        "severity": rule.severity, "enabled": rule.enabled,
        "params": dict(rule.params), "note": rule.note, "locale": rule.locale,
    }


def load_user_rule(record: Mapping) -> Rule | None:
    """A rule from a record; `None` — the record was not understood.

    We silently skip three cases: an unknown kind (a rule from a future version),
    the substitution of a built-in rule (otherwise somebody else's file could
    redefine the bracket check with an expression of its own) and a record
    without a name.
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
    """The rules of one's own in the layer, in the order of the record."""
    records = (overlay or {}).get("custom")
    if not isinstance(records, (list, tuple)):
        return ()
    loaded = (load_user_rule(r) for r in records)
    return tuple(r for r in loaded if r is not None)


# --- the built-in set ----------------------------------------------------
#
# The order of declaration = the order of checking = the order of codes in remarks.

# The examples (`example_bad`/`example_ok`) are deliberately NOT translated: they
# are not labels but the self-check of a rule. The Russian verbs in the
# `linking_calque` example are obliged to make the rule fire — translate them,
# and the rule falls silent on its own example (this is caught by
# `test_qa_defaults.py`).

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
            "QaRules", "A lost variable leaves a hole in the text in the game. A "
                       "set that merely differs is a softer case, and "
                       "«only_if_all_lost» keeps quiet about it"),
        example_bad=(("Cost: $VALUE$", "Цена"),),
        example_ok=(("Cost: $VALUE$", "Цена: $VALUE$"),),
    ),
    Rule(
        id="icon_mismatch", title=QT_TRANSLATE_NOOP("QaRules", "Icons @…! and £…£"),
        category="markup", severity=ERROR,
        message=QT_TRANSLATE_NOOP("QaRules", "Icons do not match the original"),
        note=QT_TRANSLATE_NOOP(
            "QaRules", "@gold! is the CK3 icon; the £gold£ form belongs to EU4, "
                       "HOI4 and Stellaris. Both are checked, because a "
                       "translator who has worked on another game types the icon "
                       "they are used to"),
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
            "QaRules", "The colour of HOI4, EU4 and Stellaris: §Y…§!. A lost §! "
                       "paints the rest of the line, and a swapped code can turn "
                       "a warning green"),
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
            "QaRules", "The Stellaris grammar system: «Empress&!fem,vowel» and "
                       "«A $1$|||vowel:An $1$». Variants the translator adds for "
                       "cases are fine; a lost tag is not — it changes the "
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
            "QaRules", "An edge space is often in the original too: that is how "
                       "the game glues strings together. Compared against the "
                       "source, the rule stays quiet about those"),
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
            "QaRules", "The original is often unbalanced itself, and the "
                       "translation has nothing to do with it — hence the check "
                       "against the source"),
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
    """A rule set ready to be applied."""

    def __init__(self, rules):
        self.rules: tuple[Rule, ...] = tuple(rules)
        self.by_id: dict[str, Rule] = {r.id: r for r in self.rules}
        # A rule of one's own that has eaten more than SLOW_RULE_SECONDS on a
        # single row is switched off for the rest of the pass. It piles up here
        # and not in a global variable: a set lives exactly one pass, and the
        # next one starts from a clean sheet — the rule may have stumbled over
        # one row out of a hundred thousand, and there is nothing to punish it
        # forever for.
        self.exhausted: set[str] = set()
        self.spent: dict[str, float] = {}

    # --- access ---

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
        """A dictionary compatible with the former qa.CODES."""
        return {r.id: (r.severity, self.message(r.id)) for r in self.rules}

    def restricted_to(self, codes) -> RuleSet:
        """Only the listed rules — and they are on, whatever the default may be."""
        wanted = set(codes)
        return RuleSet(replace(r, enabled=r.id in wanted) for r in self.rules)

    def with_rule(self, rule: Rule) -> RuleSet:
        return RuleSet(rule if r.id == rule.id else r for r in self.rules)

    # --- application ---

    def check(self, en_text: str, ru_text: str) -> list[str]:
        """The remark codes for a pair "source — translation".

        A rule that has eaten too much time goes out for the rest of the pass —
        see `SLOW_RULE_SECONDS` and `exhausted`.
        """
        found: list[str] = []
        for rule in self.rules:
            if not rule.enabled or rule.id in PROJECT_WIDE:
                continue
            if rule.id in self.exhausted:
                continue
            if rule.id == EMPTY:
                # An empty translation breaks off the parsing: the other remarks
                # have nothing to do with an empty row and would only flood the list.
                if not ru_text.strip():
                    return [EMPTY]
                continue
            check = check_of(rule)
            if check is None:
                continue
            started = time.perf_counter()
            try:
                hit = check(en_text, ru_text, rule.params)
            except Exception:   # noqa: BLE001 — a rule with a broken setting is quieted
                # The setting is edited by hand: `qa_rules.json` is carried
                # between machines, `.pdxqa` files are sent to one another — that
                # is what the files are for. A typo in a number
                # (`min_word_len: "три"`) reaches `int()` already inside the
                # check, and the check goes over a hundred thousand rows, so
                # falling over mid-pass because of one rule will not do. We quiet
                # it, as we already quiet a rule with an unparsable expression
                # (`_user_re`); sorting the setting out is the work of the rules
                # window.
                continue
            spent = time.perf_counter() - started
            self.spent[rule.id] = self.spent.get(rule.id, 0.0) + spent
            if rule.origin == USER and spent >= SLOW_RULE_SECONDS:
                self.exhausted.add(rule.id)
            if hit:
                found.append(rule.id)
        if not ru_text.strip():
            return []           # empty, but the rule about emptiness is off
        return found


def default_ruleset() -> RuleSet:
    return RuleSet(BUILTIN_RULES)


# --- presets -------------------------------------------------------------
#
# A preset is the same kind of delta as a user edit, only ready-made. The numbers
# in the comments were measured on the live agoot translation (136,113 rows).

CUSTOM = "custom"

PRESET_ORDER = ("strict", "ck3", "hoi4", "ck2", "stellaris", "quiet", CUSTOM)
# Only the sets that have a name of their own. The game ones are called by the
# game itself, and that name is not translated — the same rule as in
# `core/games.py`: «Crusader Kings III» is the same in every interface language.
PRESET_LABELS = {
    "strict": QT_TRANSLATE_NOOP("QaRules", "Strict"),
    "quiet": QT_TRANSLATE_NOOP("QaRules", "Breakage only"),
    CUSTOM: QT_TRANSLATE_NOOP("QaRules", "Own"),
}


def preset_label(name: str) -> str:
    """The label of a set in the interface language. A game stays itself."""
    if name in PRESET_LABELS:
        return translate("QaRules", PRESET_LABELS[name])
    return games.title(name)

# What the sets were called before 0.1.2, when the game and the language were
# glued into one preset. The names lie in users' qa_rules.json, in the overlays
# inside project files and in exported .pdxqa — reading them will always be
# necessary.
PRESET_ALIASES = {"ck3_ru": "ck3", "hoi4_ru": "hoi4",
                  "ck2_ru": "ck2", "stellaris_ru": "stellaris"}
PRESET_NOTES = {
    "strict": QT_TRANSLATE_NOOP(
        "QaRules", "Every rule on, nothing forgiven. For the final read-through, "
                   "when you would rather sift ten false alarms than miss one "
                   "real fault."),
    "ck3": QT_TRANSLATE_NOOP(
        "QaRules", "What a CK3 translator does on purpose stops counting as a "
                   "mistake: a reference wrapped so it can be inflected, an "
                   "added #L, formatting flags. The helpers your language uses "
                   "are added on their own."),
    "hoi4": QT_TRANSLATE_NOOP(
        "QaRules", "HOI4 gives each language its own inflection helpers, and a "
                   "translation swaps plain references for them. This set knows "
                   "them, so a swap stops reading as a loss."),
    "ck2": QT_TRANSLATE_NOOP(
        "QaRules", "CK2 translations inflect nearly everything and add forms of "
                   "address the English has none of. That is expected here — a "
                   "reference that went missing is still caught."),
    "stellaris": QT_TRANSLATE_NOOP(
        "QaRules", "Stellaris inflects names through a grammar system of its "
                   "own, and many terms are meant to stay as they are in the "
                   "original. Those stop shouting; anything that breaks the "
                   "text still does."),
    "quiet": QT_TRANSLATE_NOOP(
        "QaRules", "Only what breaks the text in the game: a lost variable or "
                   "icon, an unclosed tag, an empty translation. Everything "
                   "else keeps quiet."),
    CUSTOM: QT_TRANSLATE_NOOP(
        "QaRules", "The built-in values with nothing on top. Start here to set "
                   "every rule by hand."),
}

# The game itself has become the preset, so there is no table of correspondence
# any more: the set for CK3 is called «Crusader Kings III». Before 0.1.2 a pair
# of "game plus language" lay here, because the language was written into the
# preset itself.

# «(recommended)» stood right inside the `ck3_ru` label, that is, was promised to
# everyone — including the HOI4 translator, for whom a neighbouring set is the
# recommended one. The mark is separate so that it sticks to the preset that
# suits the open project, and to none at all when none is open.
RECOMMENDED_MARK = QT_TRANSLATE_NOOP(
    "QaRules", "%1 — recommended for this project")


def recommended(game: str, locale: str = "") -> str | None:
    """The set for the game of the project. `None` — it has no game of its own.

    The language no longer affects the choice of the set: it picks up its own
    layer by itself, see `language_profile`.
    """
    return game if game in PRESETS and game != CUSTOM else None


def display_order(game: str = "", locale: str = "") -> tuple[str, ...]:
    """The order of the presets on the shop window: the one for the project first.

    Without an open project (and for a pair that is not in the table)
    `PRESET_ORDER` remains: shuffling the list without knowing whose it is would
    mean changing the familiar arrangement for nothing.
    """
    first = recommended(game, locale)
    if first is None:
        return PRESET_ORDER
    return (first, *(name for name in PRESET_ORDER if name != first))


# The heads of the calls a translator wraps a substitution in for the sake of
# declension. Not a typo but a standard device: 59% of all bracket divergences
# are the replacement of an English reference by such a wrapper.
GRAMMAR_WRAPPERS = ["Concept", "Select_CString"]

# The declining functions of the Russian translations live separately
# (`core/inflections.py`): they are data taken off live trees, and their place is
# next to one another, not in the middle of a description of rules. Here — only
# the names by which the presets call them.
HOI4_RU_CALLS = inflections.HOI4_RU_CALLS
HOI4_RU_ENDINGS = inflections.HOI4_RU_ENDINGS
CK2_RU_CALLS = inflections.CK2_RU_CALLS

# What stays on in "Breakages only"
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
    "ck3": {
        # 33,703 → 26,001 (wrappers) → 13,582 (a wrapper instead of a reference)
        # → 9,955 (presentation flags of the |E kind do not count as a divergence)
        "brackets_mismatch": {"params": {
            "ignore_extra_heads": GRAMMAR_WRAPPERS,
            "allow_replacement": True,
            "ignore_flags": True,
        }},
        # 1,179 → 513: a #L added for the sake of a case is a device, not a lost tag
        "fmt_mismatch": {"params": {"allow_extra_tags": ["#L"]}},
        # 380 → 345
        "double_space": {"params": {"ignore_if_in_source": True}},
        # not an error but a reason to check — 11,449 rows with inflated severity
        "inconsistent": {"severity": INFO},
    },
    "hoi4": {
        # Measured on the vanilla Russian HOI4 (124,893 rows with a translation):
        # brackets_mismatch 5,028 → 746, glued_markup 1,249 → 5. What is left are
        # candidates for real errors, including Paradox's own typos in function
        # names and lost spaces («регионе[350.GetName],»).
        "brackets_mismatch": {"params": {
            "allow_replacement": True,
            "ignore_flags": True,
        }},
        "glued_markup": {"params": {"allow_inside_word": True}},
        # The double space arrives from the source itself — «£command_power  §Y…»
        # parts the icon and the number exactly like that. 292 → 15.
        "double_space": {"params": {"ignore_if_in_source": True}},
        # The same argument as in ck3_ru: the same source translated in different
        # ways is a reason to check, not an error.
        "inconsistent": {"severity": INFO},
    },
    "stellaris": {
        # Measured on the vanilla pair (148,751 rows with a translation): 32,969
        # → 29,525. The main source of noise here is a different one from the
        # neighbours': 17,156 rows where the translation coincided with the
        # source — those are terms and the names of species, planets and
        # modifiers. We do not switch the rule off (real untranslated text hides
        # among them), but it stops being a shout.
        "same_as_en": {"severity": INFO},
        # The Russian translator of Stellaris writes references and substitutions
        # into the variants for the cases, so "appeared in the translation" is
        # the norm here; what is lost the rules still catch.
        "brackets_mismatch": {"params": {"allow_extra": True}},
        "dollar_mismatch": {"params": {"allow_extra": True}},
        "inconsistent": {"severity": INFO},
    },
    "ck2": {
        # Measured on the vanilla pair (89,616 rows with a translation): 45,593 →
        # 24,047 in total, brackets_mismatch 21,905 → 9,924, glued_markup 13,101
        # → 3,546. `allow_extra` is no luxury here: the Russian translator of CK2
        # constantly adds an address where English has none («Ты славно
        # сража[X.GetLasLsya], [X.GetFirstName]»), and an added substitution does
        # not break the game. A lost one does, and the rule still catches it.
        "brackets_mismatch": {"params": {
            "allow_replacement": True,
            "allow_extra": True,
            "ignore_flags": True,
        }},
        "glued_markup": {"params": {"allow_inside_word": True}},
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


# --- the language layer --------------------------------------------------
#
# What is left of a preset once the game has been taken out of it: the lists of
# functions with which a translation into a particular language mends the
# grammar. A pair of "game plus language", because the names are given by the
# game and the need for them by the language. The layer is not chosen by a human:
# it is picked up by the target language of the open project, and that is exactly
# why the name of a set no longer needs the word "Russian".
#
# The data and the way it was taken off are in `core/inflections.py`.


def language_profile(preset: str, locale: str) -> dict | None:
    """The delta of a language over the game profile. `None` — no such pair, nothing to tell."""
    calls = inflections.calls(preset, locale)
    if not calls:
        return None
    delta: dict = {"brackets_mismatch": {"params": {"ignore_extra_tails": calls}}}
    if (glued := inflections.endings(preset, locale)):
        delta["glued_markup"] = {"params": {"ending_calls": glued}}
    return delta


# --- overlays: a delta over the set --------------------------------------

OVERLAY_VERSION = 1


def _rule_with_delta(rule: Rule, delta: Mapping) -> Rule:
    """A rule with the delta applied. What is unknown in the delta is silently skipped.

    We skip deliberately: the overlay was written by a former version of the
    application, and the parameter may have disappeared since. The application
    must not fall over because of a setting that is no longer there — and an
    unknown key, once in `params`, would make the rule indistinguishable from a
    changed one and would settle in the delta forever.
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
    """The set with the delta `{rule id: {enabled/severity/params}}` applied."""
    if not delta:
        return rules
    return RuleSet(
        _rule_with_delta(r, delta[r.id])
        if isinstance(delta.get(r.id), Mapping) else r
        for r in rules
    )


def preset_of(overlay: Mapping | None) -> str:
    """The preset of the overlay; `custom` — if it is not set or not known.

    The former names (`ck3_ru`) are translated into the present ones: before
    0.1.2 the game and the language lived in one preset, and settings with those
    names lie on people's disks.
    """
    name = (overlay or {}).get("preset")
    name = PRESET_ALIASES.get(name, name)
    return name if name in PRESETS else CUSTOM


def for_locale(rules: RuleSet, locale: str) -> RuleSet:
    """Switch off the rules of a foreign target language.

    We switch off instead of throwing out: the rule stays visible in the setup
    window — there it is plain why it is silent — and switching it on by hand is
    still possible. A rule thrown out would look like one gone missing without
    explanation.

    An empty locale switches nothing off: the language is unknown, and being
    silent at random is worse than showing too much.
    """
    if not locale:
        return rules
    return RuleSet(
        replace(r, enabled=False) if r.locale and r.locale != locale else r
        for r in rules)


def with_user_rules(rules: RuleSet, incoming) -> RuleSet:
    """Add the rules of one's own to the set; one of the same name is replaced whole.

    A replacement and not a merge: the rule of the upper layer was written by the
    user whole, and "inherit half the parameters" would mean here getting a set
    they never assembled.
    """
    incoming = tuple(incoming)
    if not incoming:
        return rules
    by_id = {r.id: r for r in incoming}
    kept = tuple(by_id.pop(r.id, r) for r in rules)
    return RuleSet(kept + tuple(r for r in incoming if r.id in by_id))


def resolve(*overlays: Mapping | None, locale: str = "") -> RuleSet:
    """The set in force: the built-in values, the target language, then the layers.

    The language is part of the **base** and not the last touch: otherwise it
    would wipe out the deliberate choice of the user. Having switched on "a space
    is missing before the substitution" by hand in a French project, they are to
    get it — the rule is written for Russian, but the translator knows better.

    The rules of one's own in a layer arrive before its delta: the delta is
    entitled to correct them, whereas replacing a rule of one's own from a lower
    layer whole can only be done by an upper layer, and it does that with its own
    record in `custom`.
    """
    rules = for_locale(default_ruleset(), locale)
    for overlay in overlays:
        if not overlay:
            continue
        preset = preset_of(overlay)
        rules = apply_delta(rules, PRESETS.get(preset))
        rules = apply_delta(rules, language_profile(preset, locale))
        rules = with_user_rules(
            rules, for_locale(RuleSet(user_rules(overlay)), locale))
        rules = apply_delta(rules, overlay.get("rules"))
    return rules


def rule_delta(base: Rule, current: Rule) -> dict:
    """How `current` differs from `base`. Empty — the rule was not touched."""
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
    """An overlay that together with `under` gives exactly `rules`.

    `under` is the layer lying below (for a project overlay that is the global
    one): otherwise the project would write itself a copy of the global edits and
    stop following them. For the same reason only the rules that are not below
    get into `custom`: a rule set up for all projects goes on living there, while
    an edit of it in the project goes into the delta.

    `locale` is the target language `rules` was assembled on. It too has to go
    into the base and not into the delta: otherwise a French translator would
    write themselves "switch off the rules of Russian grammar", and those would
    stay switched off after a change of the project language — without a trace of
    who switched them off.
    """
    # Reading the former names we can, writing them we cannot: a file created
    # today is to carry the present name of the set.
    preset = PRESET_ALIASES.get(preset, preset)
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
    """Nothing is set up — such an overlay need not be stored at all."""
    overlay = overlay or {}
    return (preset_of(overlay) == CUSTOM
            and not overlay.get("rules") and not user_rules(overlay))

"""Comparing revisions of the original: what exactly the mod author changed.

Two jobs:
  * decide whether a change deserves the translator's attention
    (`classify_change`);
  * show where the text changed (`changed_ranges`, `word_diff`).

A word here is what the translator sees, so the comparison goes by words rather
than by characters: a per-character diff turns long descriptions into mush.
"""
from __future__ import annotations

import difflib
import re
from typing import Literal

from pdxloc.core.i18n import fill, translate
from pdxloc.core import markup

ChangeKind = Literal["cosmetic", "meaningful"]

COSMETIC = "cosmetic"
MEANINGFUL = "meaningful"

# Words together with the spaces after them, so joining the pieces gives back
# the source text
_WORD_RE = re.compile(r"\S+\s*")
_PUNCT_RE = re.compile(r"[.,;:!?…—–\-\"'`«»„“”()\[\]{}]+")
_SPACE_RE = re.compile(r"\s+")


def _markup_tokens(text: str) -> list[str]:
    """CK3 markup in order of appearance: its changes must reach the translation.

    Every pattern is searched over the whole text independently, so `#TOOLTIP:KEY`
    lands in the list twice: whole from `fmt_param` and by its head from
    `fmt_open`. That is not a fault and needs no fixing — the count is symmetric
    on both sides of the comparison, and the verdict depends only on whether the
    two lists matched.
    """
    tokens: list[str] = []
    for pattern in markup.structural_patterns():
        tokens.extend(pattern.findall(text))
    return sorted(tokens)


def normalize_for_compare(text: str) -> str:
    """The text without what does not change the meaning: markup, punctuation,
    case, whitespace."""
    for pattern in markup.structural_patterns():
        text = pattern.sub(" ", text)
    text = text.replace("\\n", " ")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip().casefold()


def classify_change(old: str, new: str) -> ChangeKind:
    """A cosmetic edit or a meaningful one.

    Cosmetic when, after punctuation, case and whitespace are stripped, the text
    is the same AND the set of markup has not changed. A change of markup counts
    as meaningful: it has to be carried into the translation even if the words
    stayed as they were.
    """
    if _markup_tokens(old) != _markup_tokens(new):
        return MEANINGFUL
    return COSMETIC if normalize_for_compare(old) == normalize_for_compare(new) else MEANINGFUL


class _Token:
    """A word together with its place in the source text.

    The comparison goes by the word itself while the highlighting goes by the
    coordinates: otherwise a word at the end of a line, with no space after it,
    counts as different from the same word in the middle.
    """

    __slots__ = ("word", "start", "end", "raw")

    def __init__(self, match: re.Match):
        self.raw = match.group()
        self.word = self.raw.strip()
        self.start = match.start()
        self.end = match.start() + len(self.raw.rstrip())

    def __eq__(self, other) -> bool:
        return isinstance(other, _Token) and self.word == other.word

    def __hash__(self) -> int:
        return hash(self.word)


def _tokens(text: str) -> list[_Token]:
    return [_Token(m) for m in _WORD_RE.finditer(text)]


def word_diff(old: str, new: str) -> list[tuple[str, str]]:
    """A word-level diff: [("equal"|"insert"|"delete", fragment), …].

    Joining the equal+insert fragments gives the new text, equal+delete the old.
    """
    old_tokens, new_tokens = _tokens(old), _tokens(new)

    def join(tokens: list[_Token], lo: int, hi: int) -> str:
        return "".join(t.raw for t in tokens[lo:hi])

    result: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            result.append(("equal", join(new_tokens, b0, b1)))
        elif op == "insert":
            result.append(("insert", join(new_tokens, b0, b1)))
        elif op == "delete":
            result.append(("delete", join(old_tokens, a0, a1)))
        else:   # replace — показываем и удалённое, и добавленное
            result.append(("delete", join(old_tokens, a0, a1)))
            result.append(("insert", join(new_tokens, b0, b1)))
    return result


def changed_ranges(old: str, new: str) -> list[tuple[int, int]]:
    """Ranges (start, end) in the NEW text that the old one did not have.

    Exactly what is needed to highlight right inside the original field.
    """
    old_tokens, new_tokens = _tokens(old), _tokens(new)
    ranges: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    for op, _a0, _a1, b0, b1 in matcher.get_opcodes():
        if op in ("insert", "replace") and b1 > b0:
            ranges.append((new_tokens[b0].start, new_tokens[b1 - 1].end))
    return _merge(ranges)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Join neighbouring ranges so the highlighting does not come in abutting
    pieces."""
    if not ranges:
        return []
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def summarize_change(old: str, new: str, limit: int = 80) -> str:
    """A short description of the edit, for the list and the tooltip."""
    kind = classify_change(old, new)
    added = "".join(t for op, t in word_diff(old, new) if op == "insert").strip()
    removed = "".join(t for op, t in word_diff(old, new) if op == "delete").strip()
    prefix = (translate("TextDiff", "cosmetic edit") if kind == COSMETIC
              else translate("TextDiff", "the text changed"))
    parts = []
    if removed:
        parts.append(fill(translate("TextDiff", "removed: %1"), removed[:limit]))
    if added:
        parts.append(fill(translate("TextDiff", "added: %1"), added[:limit]))
    return f"{prefix} — {'; '.join(parts)}" if parts else prefix

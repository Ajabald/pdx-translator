"""Сравнение редакций оригинала: что именно изменил автор мода.

Две задачи:
  * решить, стоит ли изменение внимания переводчика (`classify_change`);
  * показать, где именно текст изменился (`changed_ranges`, `word_diff`).

Слово здесь — то, что видит переводчик, поэтому сравниваем по словам, а не по
символам: посимвольный дифф на длинных описаниях превращается в кашу.
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

# Слова вместе с пробелами после них — чтобы склейка кусков давала исходный текст
_WORD_RE = re.compile(r"\S+\s*")
_PUNCT_RE = re.compile(r"[.,;:!?…—–\-\"'`«»„“”()\[\]{}]+")
_SPACE_RE = re.compile(r"\s+")


def _markup_tokens(text: str) -> list[str]:
    """Разметка CK3 в порядке появления: её изменения переводчик обязан перенести.

    Каждый паттерн ищется по всему тексту независимо, поэтому `#TOOLTIP:KEY`
    попадает в список дважды: целиком от `fmt_param` и головой от `fmt_open`.
    Это не ошибка и чинить это не надо — счёт симметричен с обеих сторон
    сравнения, а вердикт зависит только от того, совпали списки или нет.
    """
    tokens: list[str] = []
    for pattern in markup.structural_patterns():
        tokens.extend(pattern.findall(text))
    return sorted(tokens)


def normalize_for_compare(text: str) -> str:
    """Текст без того, что не меняет смысла: разметки, пунктуации, регистра, пробелов."""
    for pattern in markup.structural_patterns():
        text = pattern.sub(" ", text)
    text = text.replace("\\n", " ")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip().casefold()


def classify_change(old: str, new: str) -> ChangeKind:
    """Косметическая правка или смысловая.

    Косметическая — если после вычистки пунктуации, регистра и пробелов текст
    тот же И набор разметки не изменился. Изменение разметки считаем значимым:
    его придётся перенести в перевод, даже если слова остались прежними.
    """
    if _markup_tokens(old) != _markup_tokens(new):
        return MEANINGFUL
    return COSMETIC if normalize_for_compare(old) == normalize_for_compare(new) else MEANINGFUL


class _Token:
    """Слово с его местом в исходном тексте.

    Сравниваем по самому слову, а подсвечиваем по координатам: иначе слово в
    конце строки (без пробела после) считается отличным от такого же слова в
    середине.
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
    """Пословный дифф: [("equal"|"insert"|"delete", фрагмент), …].

    Склейка фрагментов equal+insert даёт новый текст, equal+delete — старый.
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
    """Диапазоны (начало, конец) в НОВОМ тексте, которых не было в старом.

    Ровно то, что нужно для подсветки прямо в поле оригинала.
    """
    old_tokens, new_tokens = _tokens(old), _tokens(new)
    ranges: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    for op, _a0, _a1, b0, b1 in matcher.get_opcodes():
        if op in ("insert", "replace") and b1 > b0:
            ranges.append((new_tokens[b0].start, new_tokens[b1 - 1].end))
    return _merge(ranges)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Склеить соседние диапазоны, чтобы не плодить подсветку встык."""
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
    """Короткое описание правки для списка и подсказки."""
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

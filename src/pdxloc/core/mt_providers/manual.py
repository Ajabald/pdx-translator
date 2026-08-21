"""The manual web route: translation through a browser, no keys at all.

The trick is carried over from ESP/ESM Translator. The tool joins a batch of rows
with numbered separators, the person pastes it into any web translator, brings
the result back, and the tool cuts it apart again. No key is needed, it works
with anything — and it is the only route open to someone with no subscription.

**The separators are numbered, and that is the whole point.** An unnumbered
separator catches a lost row only; a numbered one also catches a reordering — and
a translation that lands on somebody else's key looks like finished work and is
found weeks later. On any mismatch the batch is not applied at all.

The module never touches the network: `join` and `split` are ordinary functions,
tested without Qt and without a socket.
"""
from __future__ import annotations

import re

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.mt_errors import MtResponseError
from pdxloc.core.mt_providers import ProviderConfig

DEFAULT_SEPARATOR = "===%d==="


def _line(separator: str, index: int) -> str:
    return separator.replace("%d", str(index))


def join(texts: list[str], separator: str = DEFAULT_SEPARATOR) -> str:
    """Join a batch for pasting into a translator."""
    parts: list[str] = []
    for index, text in enumerate(texts):
        parts.append(_line(separator, index))
        parts.append(text)
    return "\n".join(parts)


def _pattern(separator: str) -> re.Pattern:
    head, _, tail = separator.partition("%d")
    return re.compile(rf"^[ \t]*{re.escape(head)}\s*(\d+)\s*{re.escape(tail)}[ \t]*$",
                      re.M)


def split(text: str, count: int, separator: str = DEFAULT_SEPARATOR) -> list[str]:
    """Cut the answer back apart. Any mismatch refuses the whole batch.

    It is not only the count that is checked: the numbers must run consecutively
    from zero. A service that swapped two pieces around would otherwise pass
    unnoticed.
    """
    marks = list(_pattern(separator).finditer(text))
    numbers = [int(m.group(1)) for m in marks]
    if numbers != list(range(count)):
        raise MtResponseError(fill(translate(
            "Mt", "The answer has %1 separators instead of %2, or their order "
                  "changed. Nothing from this batch was applied."),
            len(marks), count))

    result: list[str] = []
    for i, mark in enumerate(marks):
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        result.append(text[start:end].strip("\n"))
    return result


class ManualProvider:
    """Formally a provider, in fact a pipeline with no transport.

    It implements the same contract as the others so that the selection, the
    markup shielding, the undo batch and the summary all behave identically. It
    translates nothing itself: a person in a browser does that, and nobody ever
    calls `translate_batch` here.
    """

    name = "manual"
    label = QT_TRANSLATE_NOOP("Mt", "Manual — through a web translator")
    needs_key = False
    char_limit = 100_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return True

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str | None]:
        raise MtResponseError(translate(
            "Mt", "The manual mode is driven from its own tab, not from here."))

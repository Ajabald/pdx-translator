"""Shielding CK3 markup during machine translation.

Translators — services and people alike — happily break `[GetTrait('x').GetName]`,
`$VALUE$`, `@gold!` and `#bold …#!`. Before sending, such pieces are replaced with
short untranslatable placeholders and put back afterwards.

There are two forms of placeholder, and that is not a whim:

* `⟦N⟧` by default. The characters are rare, services take them for punctuation
  and leave them alone;
* `{{N}}` for the manual route. There the text passes through a browser input
  field and the clipboard, and that is exactly where U+27E6 gets mangled or
  disappears outright. `unshield` always understands both forms — what has to be
  restored is not necessarily what we sent.

The providers live in `core/mt_providers/`, the orchestration of a run in
`core/mt_run.py`. Here there is only the markup and the registry.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pdxloc.core import markup
from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_providers import PROVIDERS, ProviderConfig, get, labels

# The composition and the order live in core/markup.py: the closing #! must be
# searched for before the opening tags, and @name! after [ … ], or an icon
# inside a scripted call steals the range of the whole bracket.
_SHIELDED = markup.shield_tokens()

# Both forms of the placeholder, allowing for inserted spaces: translators are
# fond of «⟦ 3 ⟧», and editors of turning {{3}} into { {3} }.
_TOKEN_RE = re.compile(r"⟦\s*(\d+)\s*⟧|\{\s*\{\s*(\d+)\s*\}\s*\}")

UNICODE_TOKENS = "unicode"
ASCII_TOKENS = "ascii"


def _token(index: int, kind: str) -> str:
    return f"{{{{{index}}}}}" if kind == ASCII_TOKENS else f"⟦{index}⟧"


def shield_tags(text: str, kind: str = UNICODE_TOKENS) -> tuple[str, dict[str, str]]:
    """Replace the markup with placeholders. Returns (shielded text, the mapping)."""
    mapping: dict[str, str] = {}
    out: list[str] = []
    last = 0
    for start, end in markup.spans(text, _SHIELDED):
        token = _token(len(mapping), kind)
        mapping[token] = text[start:end]
        out.append(text[last:start])
        out.append(token)
        last = end
    out.append(text[last:])
    return "".join(out), mapping


_DIGITS_RE = re.compile(r"\d+")


def _index(match: re.Match) -> str:
    """The number of a placeholder, whichever of the two forms it takes."""
    return match.group(1) or match.group(2)


def _number(token: str) -> str:
    """The number out of the placeholder itself: «⟦7⟧» and «{{7}}» are both 7."""
    found = _DIGITS_RE.search(token)
    return found.group(0) if found else ""


def _by_number(mapping: dict[str, str]) -> dict[str, str]:
    """The mapping keyed by number: we do not control the form in the answer."""
    return {_number(token): value for token, value in mapping.items()}


def unshield(text: str, mapping: dict[str, str]) -> str:
    """Put the markup back.

    Restoring goes **by number** rather than by the exact look of a placeholder:
    a service may have inserted spaces inside, and the manual route may bring
    back the other form of brackets. An unfamiliar number is left as it is: there
    is nothing to invent on the translator's behalf.
    """
    by_number = _by_number(mapping)
    return _TOKEN_RE.sub(lambda m: by_number.get(_index(m), m.group(0)), text)


def missing_tokens(text: str, mapping: dict[str, str]) -> list[str]:
    """The placeholders the translation lost: a sign the result is broken."""
    present = {_index(m) for m in _TOKEN_RE.finditer(text)}
    return [token for token in mapping if _number(token) not in present]


@runtime_checkable
class TranslationProvider(Protocol):
    """A machine translation provider.

    It receives already shielded texts and must return the same number of rows in
    the same order. Matching goes by position, and that is the only thing to lean
    on: identical originals are an everyday matter in a project, and matching by
    text would mix them up.

    `None` may be returned instead of a string; it means «this row could not be
    translated». The concession was needed for the LLM providers: they do not
    always give N answers to N requests, and dropping a batch of fifty over one
    row would be wasteful. The classic services do not use it.
    """

    name: str
    label: str
    char_limit: int

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        ...

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str | None]:
        ...


def get_provider(name: str, config: ProviderConfig | None = None):
    """A provider by name. An unknown name gives the stub (see `mt_providers.get`)."""
    return get(name, config)


def provider_labels() -> dict[str, str]:
    return labels()


def translate_texts(
    provider: TranslationProvider,
    texts: list[str],
    src_locale: str,
    tgt_locale: str,
) -> list[tuple[str | None, list[str]]]:
    """Translate the texts with the markup kept intact.

    Returns pairs of (translation, lost placeholders). A `None` translation means
    the provider could not manage that row; the second half is filled in when the
    markup came back damaged and the result needs checking by hand.
    """
    shielded, mappings = [], []
    for text in texts:
        s, mapping = shield_tags(text)
        shielded.append(s)
        mappings.append(mapping)

    translated = provider.translate_batch(shielded, src_locale, tgt_locale)
    if len(translated) != len(texts):
        raise RuntimeError(
            fill(translate("Mt", "The provider returned %1 rows instead of %2"),
                 len(translated), len(texts)))

    result = []
    for raw, mapping in zip(translated, mappings, strict=True):
        if raw is None:
            result.append((None, []))
            continue
        result.append((unshield(raw, mapping), missing_tokens(raw, mapping)))
    return result


# --- access keys ---

_KEY_PREFIX = "mt/key/"


def api_key(provider: str) -> str:
    """The provider key in the clear, only to be handed to a request."""
    from pdxloc import settings
    from pdxloc.core import secrets

    stored = str(settings.qsettings().value(f"{_KEY_PREFIX}{provider}", "") or "")
    return secrets.unprotect(stored)


def save_api_key(provider: str, key: str) -> None:
    from pdxloc import settings
    from pdxloc.core import secrets

    settings.qsettings().setValue(
        f"{_KEY_PREFIX}{provider}", secrets.protect(key.strip()))


def forget_api_key(provider: str) -> None:
    from pdxloc import settings

    settings.qsettings().setValue(f"{_KEY_PREFIX}{provider}", "")


def key_is_protected(provider: str) -> bool:
    """Whether the system protects the key. «Preferences» must show the truth."""
    from pdxloc import settings
    from pdxloc.core import secrets

    stored = str(settings.qsettings().value(f"{_KEY_PREFIX}{provider}", "") or "")
    return secrets.is_protected(stored)


__all__ = [
    "ASCII_TOKENS", "PROVIDERS", "ProviderConfig", "TranslationProvider",
    "UNICODE_TOKENS", "api_key", "forget_api_key", "get_provider",
    "key_is_protected", "missing_tokens", "provider_labels", "save_api_key",
    "shield_tags", "translate_texts", "unshield",
]

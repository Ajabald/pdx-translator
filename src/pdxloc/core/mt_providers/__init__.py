"""Machine translation providers: the registry and the shared contract.

One file per service. Each describes only its own affairs: the address, the
header carrying the key, the shape of the request and the answer, its own error
codes and **its own language mapping**. The last of those lives with the provider
deliberately: `EN-GB` and `PT-BR` are DeepL's rule rather than common knowledge,
and a single «language × service» matrix would go stale on the first change to
somebody else's API while remaining the one place nobody ever looks.

A provider does not read the settings: it is handed a ready `ProviderConfig`.
Otherwise `core/` would drag in `settings`, and Qt behind it — while the core
must import without PySide6 at all (see `tests/test_i18n.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pdxloc.core.i18n import QT_TRANSLATE_NOOP


@dataclass(frozen=True)
class ProviderConfig:
    """Everything a provider needs to know from outside.

    Assembled by the caller — the interface — rather than read from the settings:
    that keeps a provider testable with no environment and no Qt.
    """

    api_key: str = ""
    pro: bool = False                # with DeepL this is another address, not a plan
    model: str = ""                  # for the LLM ones; empty means the provider's default
    prompt: str = ""                 # the user's wishes for the LLM, not the contract
    extra: dict[str, str] = field(default_factory=dict)   # e.g. the Yandex folder_id
    timeout: float = 30.0


class NoneProvider:
    """A stub: no translation, the text comes back as it was.

    It is not only for the tests. With it the whole pipeline — selection,
    batching, statuses, undo, summary — can be exercised on a live project
    without spending a single request.
    """

    name = "none"
    label = QT_TRANSLATE_NOOP("Mt", "Off")
    char_limit = 1_000_000
    needs_key = False

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return True

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str]:
        return list(texts)


# Name -> class; the order here is the order in the «Preferences» list.
# Filled lazily: the provider modules import this same file for
# `ProviderConfig`, and building the dict in place would make a cycle.
PROVIDERS: dict[str, type] = {
    NoneProvider.name: NoneProvider,
}

_LOADED = False


def _load() -> None:
    """Pull the providers in on first use."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from pdxloc.core.mt_providers.claude import ClaudeProvider
    from pdxloc.core.mt_providers.deepl import DeepLProvider
    from pdxloc.core.mt_providers.google import GoogleProvider
    from pdxloc.core.mt_providers.manual import ManualProvider
    from pdxloc.core.mt_providers.openai import OpenAIProvider
    from pdxloc.core.mt_providers.yandex import YandexProvider

    for cls in (DeepLProvider, ClaudeProvider, OpenAIProvider,
                GoogleProvider, YandexProvider, ManualProvider):
        PROVIDERS.setdefault(cls.name, cls)


def labels() -> dict[str, str]:
    """Name -> the label for the interface, not yet translated."""
    _load()
    return {name: cls.label for name, cls in PROVIDERS.items()}


def get(name: str, config: ProviderConfig | None = None):
    """A provider by name. An unknown name gives the stub, not an exception.

    The setting may have been written by a newer version and opened by an older
    one; there is nothing to translate with, but nothing worth crashing over
    when a project is opened either.
    """
    _load()
    factory = PROVIDERS.get(name) or NoneProvider
    return factory(config or ProviderConfig())

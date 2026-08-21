"""DeepL.

The only one of the classic services with a sane multi-row request: `text` is
repeated and the answer arrives as an array in the same order. No separators are
needed at all — and with them goes the whole class of faults where a translation
lands on somebody else's key.

Free and Pro are **different addresses**, not a plan on one. A key for one does
not work on the other, and the error that comes back reads as «bad key», which
misleads; that is why the switch in «Preferences» is named after the address
rather than the plan.
"""
from __future__ import annotations

import json

from pdxloc.core.i18n import QT_TRANSLATE_NOOP
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers._http import request_json

FREE_URL = "https://api-free.deepl.com/v2"
PRO_URL = "https://api.deepl.com/v2"

# The source language is a plain code; for some languages the target one needs a
# region as well. This is DeepL's own rule and it lives here rather than in a
# shared table: a general «language × service» matrix would go stale on the first
# change to somebody else's API.
_SOURCE = {
    "en": "EN", "ru": "RU", "de": "DE", "fr": "FR", "es": "ES", "it": "IT",
    "pt": "PT", "pl": "PL", "tr": "TR", "uk": "UK", "cs": "CS", "ja": "JA",
    "ko": "KO", "zh": "ZH",
}
_TARGET = dict(_SOURCE, en="EN-GB", pt="PT-BR")


class DeepLProvider:
    name = "deepl"
    label = "DeepL"
    needs_key = True
    # The documented request limit is 128 KiB; we leave room for the service
    # fields so that a refusal comes from our own planner, not from DeepL.
    char_limit = 100_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    @property
    def base_url(self) -> str:
        return PRO_URL if self.config.pro else FREE_URL

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return src_locale in _SOURCE and tgt_locale in _TARGET

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"DeepL-Auth-Key {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str]:
        payload = {
            "text": list(texts),
            "target_lang": _TARGET.get(tgt_locale, tgt_locale.upper()),
        }
        source = _SOURCE.get(src_locale)
        if source:
            payload["source_lang"] = source

        answer = request_json(
            f"{self.base_url}/translate",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            timeout=self.config.timeout,
            service=self.label,
            # 456 is an exhausted quota: with DeepL that is not a 429
            quota_codes=(429, 456),
            opener=self.config.extra.get("opener"),
        )
        return [item.get("text", "") for item in answer.get("translations", [])]

    def usage(self) -> tuple[int, int] | None:
        """(used, limit) characters for the period — or None.

        Shown for DeepL alone, because DeepL alone reports it. For the others the
        same spot in «Preferences» stays empty: an invented number is worse than
        a missing one.
        """
        answer = request_json(
            f"{self.base_url}/usage",
            method="GET",
            headers=self._headers(),
            timeout=self.config.timeout,
            service=self.label,
            quota_codes=(429, 456),
            opener=self.config.extra.get("opener"),
        )
        if "character_count" not in answer:
            return None
        return int(answer["character_count"]), int(answer.get("character_limit", 0))


USAGE_HINT = QT_TRANSLATE_NOOP("Prefs", "Used %1 of %2 characters")

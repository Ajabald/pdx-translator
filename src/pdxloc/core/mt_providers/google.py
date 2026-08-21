"""Google Cloud Translation v2.

The official endpoint, the one that takes a key. The undocumented
`translate_a/single` that ESP/ESM Translator sits on is deliberately not used
here: the terms of service do not provide for it, and a tool translators install
for the long haul should not depend on somebody else's overlooked loophole.

**The answer always goes through HTML unescaping.** v2 returns `&#39;` for an
apostrophe and `&amp;` for an ampersand even with `format=text`. Skip that step
and an apostrophe in English text turns into rubbish while the translation still
looks fine — a mistake everyone runs into exactly once.
"""
from __future__ import annotations

import html
import json

from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers._http import request_json

URL = "https://translation.googleapis.com/language/translate/v2"

_LANGS = {
    "en": "en", "ru": "ru", "de": "de", "fr": "fr", "es": "es", "it": "it",
    "pt": "pt", "pl": "pl", "tr": "tr", "uk": "uk", "cs": "cs", "ja": "ja",
    "ko": "ko", "zh": "zh-CN",
}


class GoogleProvider:
    name = "google"
    label = "Google Cloud Translation"
    needs_key = True
    char_limit = 30_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return src_locale in _LANGS and tgt_locale in _LANGS

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str]:
        payload = {
            "q": list(texts),
            "source": _LANGS.get(src_locale, src_locale),
            "target": _LANGS.get(tgt_locale, tgt_locale),
            "format": "text",
        }
        answer = request_json(
            f"{URL}?key={self.config.api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=self.config.timeout,
            service=self.label,
            # With Google an exhausted quota arrives as the same 403 as a bad
            # key; the two are told apart by the body alone, and on an error we
            # have no body. We read 403 as a key refusal: that is the commoner
            # case and a person can fix it, while for a quota the service
            # usually answers 429.
            quota_codes=(429,),
            auth_codes=(401, 403),
            opener=self.config.extra.get("opener"),
        )
        items = answer.get("data", {}).get("translations", [])
        return [html.unescape(item.get("translatedText", "")) for item in items]

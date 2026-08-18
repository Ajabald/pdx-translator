"""Google Cloud Translation v2.

Официальный эндпоинт с ключом. Недокументированный `translate_a/single`, на
котором сидит ESP/ESM Translator, здесь не используется намеренно: он не
предусмотрен условиями использования, и инструмент, который переводчики ставят
себе надолго, не должен зависеть от чужой недосмотренной лазейки.

**Ответ обязательно проходит через HTML-развёртку.** v2 отдаёт `&#39;` вместо
апострофа и `&amp;` вместо амперсанда даже при `format=text`. Без этого шага
апостроф в английском тексте превращается в мусор, а перевод выглядит рабочим —
ошибка, на которую натыкаются все и по одному разу.
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
            # У Google исчерпанный лимит приходит тем же 403, что и неверный
            # ключ; различить их можно только по телу, а тела при ошибке у нас
            # нет. Считаем 403 отказом по ключу — это чаще и чинится человеком,
            # а по лимиту сервис обычно отвечает 429.
            quota_codes=(429,),
            auth_codes=(401, 403),
            opener=self.config.extra.get("opener"),
        )
        items = answer.get("data", {}).get("translations", [])
        return [html.unescape(item.get("translatedText", "")) for item in items]

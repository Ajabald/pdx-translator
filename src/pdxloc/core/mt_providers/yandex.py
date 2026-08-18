"""Yandex Cloud Translate (v2).

Не путать с `translate.yandex.net/api/v1.5`, на котором сидит ESP/ESM
Translator: тот выключен.

**Одного ключа не хватает — нужен ещё идентификатор каталога.** Без него сервис
отвечает отказом авторизации, и человек ищет ошибку в ключе, которого не
касался. Поэтому поле заведено отдельным и объяснено прямо в «Параметрах», а не
спрятано в `extra`.
"""
from __future__ import annotations

import json

from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import MtAuthError
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers._http import request_json

URL = "https://translate.api.cloud.yandex.net/translate/v2/translate"

_LANGS = {
    "en": "en", "ru": "ru", "de": "de", "fr": "fr", "es": "es", "it": "it",
    "pt": "pt", "pl": "pl", "tr": "tr", "uk": "uk", "cs": "cs", "ja": "ja",
    "ko": "ko", "zh": "zh",
}


class YandexProvider:
    name = "yandex"
    label = "Yandex Translate"
    needs_key = True
    char_limit = 10_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return src_locale in _LANGS and tgt_locale in _LANGS

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str]:
        folder_id = (self.config.extra.get("folder_id") or "").strip()
        if not folder_id:
            # Отказываем до запроса: иначе сервис ответит «неверный ключ», и
            # человек будет искать ошибку там, где её нет.
            raise MtAuthError(fill(translate(
                "Mt", "%1 also needs a folder id — fill it in "
                      "«File → Preferences → Machine translation»."), self.label))

        payload = {
            "folderId": folder_id,
            "texts": list(texts),
            "sourceLanguageCode": _LANGS.get(src_locale, src_locale),
            "targetLanguageCode": _LANGS.get(tgt_locale, tgt_locale),
            "format": "PLAIN_TEXT",
        }
        answer = request_json(
            URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Api-Key {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.config.timeout,
            service=self.label,
            opener=self.config.extra.get("opener"),
        )
        return [item.get("text", "") for item in answer.get("translations", [])]

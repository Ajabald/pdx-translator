"""DeepL.

Единственный из классических сервисов, у кого многострочный запрос устроен
по-человечески: `text` повторяется, и ответ приходит массивом в том же порядке.
Разделители не нужны вовсе — а значит, отпадает и весь класс ошибок, где
перевод приземляется на чужой ключ.

Free и Pro — **разные адреса**, а не тариф на одном. Ключ от одного на другом
не работает, и ошибка при этом приходит как «неверный ключ», что сбивает с
толку; поэтому переключатель в «Параметрах» назван адресом, а не тарифом.
"""
from __future__ import annotations

import json

from pdxloc.core.i18n import QT_TRANSLATE_NOOP
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers._http import request_json

FREE_URL = "https://api-free.deepl.com/v2"
PRO_URL = "https://api.deepl.com/v2"

# Исходный язык — простой код, целевой у части языков требует региона.
# Это правило DeepL, и живёт оно здесь, а не в общей таблице: общая матрица
# «язык × сервис» протухла бы на первом же изменении чужого API.
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
    # Документированный предел запроса — 128 КиБ; берём с запасом на служебные
    # поля, чтобы отказ приходил от нашего планировщика, а не от сервиса.
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
            # 456 — исчерпанная квота: у DeepL это не 429
            quota_codes=(429, 456),
            opener=self.config.extra.get("opener"),
        )
        return [item.get("text", "") for item in answer.get("translations", [])]

    def usage(self) -> tuple[int, int] | None:
        """(израсходовано, предел) символов за период — или None.

        Показывается только у DeepL, потому что только он это отдаёт. У
        остальных в «Параметрах» на этом месте пусто: выдуманное число хуже
        отсутствующего.
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

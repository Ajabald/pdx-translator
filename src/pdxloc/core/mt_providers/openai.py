"""OpenAI.

Второй провайдер с языковой моделью; общая часть — договор о формате, разбор и
деградация — в `_llm.py`. Схема ответа передаётся через `response_format`
(`json_schema` со `strict`), поэтому форма гарантирована сервисом, а не
уговорами в промпте.
"""
from __future__ import annotations

import json

from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import MtResponseError
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers import _llm
from pdxloc.core.mt_providers._http import request_json

URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"


class OpenAIProvider:
    name = "openai"
    label = "OpenAI"
    needs_key = True
    char_limit = 20_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return bool(src_locale and tgt_locale)

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str | None]:
        system = _llm.build_prompt(self.config.prompt, src_locale, tgt_locale)

        def ask(chunk: list[str]) -> str:
            payload = {
                "model": self.config.model or DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": _llm.build_payload(chunk)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "translations",
                        "strict": True,
                        "schema": _llm.SCHEMA,
                    },
                },
            }
            answer = request_json(
                URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.config.timeout,
                service=self.label,
                opener=self.config.extra.get("opener"),
            )
            choices = answer.get("choices") or []
            if not choices:
                raise MtResponseError(fill(translate(
                    "Mt", "%1 returned an answer that could not be read."),
                    self.label))
            return (choices[0].get("message") or {}).get("content") or ""

        return _llm.translate_with_fallback(ask, texts)

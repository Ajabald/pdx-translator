"""Claude API (Anthropic).

Обращаемся напрямую по HTTP, а не официальным SDK, сознательно: единственная
зависимость приложения — PySide6, и ради шести POST-запросов вторую не заводим.
Для одного эндпоинта `/v1/messages` это оправдано.

Три вещи, которые легко сделать неправильно по памяти:

* **`temperature` на Opus 5 не принимается вовсе** — параметров сэмплирования у
  модели больше нет, и запрос с ними отвергается с кодом 400. Ровность ответа
  задаётся промптом и низким усилием;
* **структурированный вывод** (`output_config.format`) гарантирует форму ответа
  на уровне сервиса. С ним разбор перестаёт быть местом, где всё ломается, а
  деградация до запроса по строке остаётся редким путём;
* **отказ приходит как успех.** Классификаторы безопасности отвечают HTTP 200 с
  `stop_reason: "refusal"` и пустым содержимым — код, читающий `content[0]` не
  глядя, на этом падает.

Усилие держим низким: перевод строки локализации — не та задача, ради которой
стоит платить за размышления. Сами размышления при этом не выключаем: у Opus 5
выключение чревато утечкой служебных тегов в ответ, а это прямо испортило бы
перевод.
"""
from __future__ import annotations

import json

from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import MtResponseError
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers import _llm
from pdxloc.core.mt_providers._http import request_json

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-opus-5"

EFFORT = "low"
MAX_TOKENS = 8192


class ClaudeProvider:
    name = "claude"
    label = "Claude API"
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
                "max_tokens": MAX_TOKENS,
                "system": system,
                "output_config": {
                    "effort": EFFORT,
                    "format": {"type": "json_schema", "schema": _llm.SCHEMA},
                },
                "messages": [{"role": "user",
                              "content": _llm.build_payload(chunk)}],
            }
            answer = request_json(
                URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "x-api-key": self.config.api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                timeout=self.config.timeout,
                service=self.label,
                # 529 — сервис перегружен: это «подожди», а не «ты не прав»
                quota_codes=(429, 529),
                opener=self.config.extra.get("opener"),
            )
            if answer.get("stop_reason") == "refusal":
                raise MtResponseError(fill(translate(
                    "Mt", "%1 declined to translate this batch."), self.label))
            blocks = answer.get("content") or []
            parts = [b.get("text", "") for b in blocks
                     if isinstance(b, dict) and b.get("type") == "text"]
            if not parts:
                raise MtResponseError(fill(translate(
                    "Mt", "%1 returned an answer that could not be read."),
                    self.label))
            return "".join(parts)

        return _llm.translate_with_fallback(ask, texts)

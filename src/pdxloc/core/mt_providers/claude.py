"""Claude API (Anthropic).

We speak plain HTTP rather than use the official SDK, and that is deliberate: the
application has exactly one dependency, PySide6, and a second one is not worth
six POST requests. For a single `/v1/messages` endpoint the trade is fair.

Three things that are easy to get wrong from memory:

* **`temperature` is not accepted by Opus 5 at all** — the model no longer takes
  sampling parameters, and a request carrying them is rejected with a 400. The
  evenness of the answer comes from the prompt and from low effort instead;
* **structured output** (`output_config.format`) guarantees the shape of the
  answer at the service level. With it, parsing stops being the place where
  everything breaks, and falling back to one request per row stays a rare path;
* **a refusal arrives as a success.** The safety classifiers answer HTTP 200 with
  `stop_reason: "refusal"` and empty content — code that reads `content[0]`
  without looking falls over right there.

Effort is kept low: translating a localisation row is not a task worth paying to
think about. Thinking itself is not switched off, though: with Opus 5, switching
it off risks service tags leaking into the answer, which would spoil the
translation outright.
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
                # 529 means the service is overloaded: that is «wait», not «you are wrong»
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

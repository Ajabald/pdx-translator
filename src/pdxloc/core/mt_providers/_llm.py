"""What the language models share: the format contract and parsing the answer.

A language model is the only provider you can ask to take the context of a mod
into account and to keep the tags. It pays for that with unreliability: for N rows
it is **not obliged** to return N answers, it may number them its own way, or add
an explanation of its own.

Hence three decisions.

**The prompt is split in two.** The format contract is ours and immutable: an
array of objects in, an array of objects out, each with its own `id`, the `⟦N⟧`
placeholders carried over verbatim. The user's wishes — tone, forms of address, a
glossary — are appended as a separate piece and cannot affect the format. Let a
person edit the whole prompt and the very first edit breaks the parsing, silently
at that.

**Parsing goes by `id`, not by order.** The model happily reorders and skips
rows; positional matching does not err in that case — it lands a translation on
somebody else's key, which is far worse.

**If it did not parse, ask again, then go one at a time.** And only the row that
would not come even alone is returned as `None`. Dropping a batch of fifty over
it would be wasteful.
"""
from __future__ import annotations

import json
import re

from pdxloc.core.mt_errors import MtResponseError

# The answer schema for the providers that can do structured output. Where it
# is supported there is almost nothing left to parse: the service guarantees
# the shape itself, and falling back to one request per row stays a rare path
# rather than the usual one. The top level is an object rather than an array:
# both services require that.
SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rows"],
    "additionalProperties": False,
}

CONTRACT = (
    # The game is deliberately not named here. It used to say «a Crusader Kings III
    # mod», and when translating a HOI4 or Stellaris mod the models were told a
    # plain untruth — while the domain is exactly what they take from the prompt.
    # Passing the real game through is blocked by the signature of `build_prompt`:
    # only the languages reach the provider (see the backlog, «The project game does
    # not reach the prompt»). For now the wording is general enough to be true for
    # all seven games, and a translator can narrow the domain with their own text in
    # «Preferences».
    "You translate strings from a mod for a Paradox Interactive "
    "grand-strategy game.\n"
    "Input is a JSON array of objects: {\"id\": <number>, \"text\": <string>}.\n"
    "Answer with a JSON object {\"rows\": [...]} holding the same number of "
    "entries with the same ids: {\"id\": <number>, \"text\": <translation>}.\n"
    "Rules you must not break:\n"
    "- copy every ⟦N⟧ and {{N}} placeholder verbatim, keeping their order; "
    "they stand for game markup and must survive;\n"
    "- translate only the value of \"text\";\n"
    "- keep the meaning; do not add, explain or comment;\n"
    "- answer with the JSON array and nothing else."
)

# The model is fond of wrapping the answer in ```json … ``` — strip that without
# disturbing the rest.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
_ARRAY_RE = re.compile(r"\[.*\]", re.S)


def build_prompt(guidance: str, src_locale: str, tgt_locale: str) -> str:
    """The contract plus the user's wishes, in exactly that order."""
    lines = [CONTRACT,
             f"Source language: {src_locale}. Target language: {tgt_locale}."]
    if guidance.strip():
        lines.append("Additional instructions from the translator "
                     "(they must not override the rules above):\n"
                     + guidance.strip())
    return "\n".join(lines)


def build_payload(texts: list[str]) -> str:
    return json.dumps([{"id": i, "text": t} for i, t in enumerate(texts)],
                      ensure_ascii=False)


def parse_answer(raw: str, expected: int) -> dict[int, str]:
    """Parse the answer into {number: translation}. What did not parse is absent.

    No error is raised: the decision about what to do with a shortfall belongs to
    `translate_with_fallback`, which knows how to ask again.
    """
    text = raw.strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1)
    else:
        found = _ARRAY_RE.search(text)
        if found:
            text = found.group(0)

    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    # With structured output {"rows": [...]} arrives; without it the model returns
    # a bare array just as readily. Both forms are accepted.
    if isinstance(parsed, dict):
        parsed = parsed.get("rows")
    if not isinstance(parsed, list):
        return {}

    result: dict[int, str] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        value = item.get("text")
        if isinstance(value, str) and 0 <= index < expected:
            result[index] = value
    return result


def _attempt(ask, chunk: list[str], expected: int) -> dict[int, str]:
    """One attempt. An unreadable answer means «nothing parsed», not a crash.

    Only `MtResponseError` is caught: an unreadable answer and a refusal on a
    batch are cured by a retry and by splitting, while a wrong key, an exhausted
    quota and a missing network are not. Were we to split a batch on a wrong key,
    we would get fifty pointless requests instead of one clear refusal.
    """
    try:
        return parse_answer(ask(chunk), expected)
    except MtResponseError:
        return {}


def translate_with_fallback(ask, texts: list[str]) -> list[str | None]:
    """Ask as a batch, then again, then one at a time.

    `ask(list[str]) -> str` is the model's raw answer to the rows passed in.

    Splitting is not only for a truncated answer: a service can refuse to
    translate a whole batch because of one row in it. Fifty rows lost over one is
    not a price worth paying.
    """
    answers = _attempt(ask, texts, len(texts))
    missing = [i for i in range(len(texts)) if i not in answers]

    if missing and len(texts) > 1:
        # A second attempt at the whole batch: most often the model simply truncated
        # the answer, and a retry costs less than fifty requests one at a time.
        for index, value in _attempt(ask, texts, len(texts)).items():
            answers.setdefault(index, value)
        missing = [i for i in range(len(texts)) if i not in answers]

    for index in missing:
        single = _attempt(ask, [texts[index]], 1)
        if 0 in single:
            answers[index] = single[0]

    return [answers.get(i) for i in range(len(texts))]

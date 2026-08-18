"""Общее для языковых моделей: договор о формате и разбор ответа.

Языковая модель — единственный провайдер, которого можно попросить учесть
контекст мода и сохранить теги. За это она платит ненадёжностью: на N строк
она **не обязана** вернуть N ответов, может пронумеровать их по-своему или
добавить пояснение от себя.

Отсюда три решения.

**Промпт разделён надвое.** Договор о формате — наш и неизменяемый: массив
объектов на входе, массив объектов на выходе, у каждого свой `id`, метки
`⟦N⟧` переносятся дословно. Пожелания пользователя (тон, обращение, глоссарий)
дописываются отдельным куском и на формат влиять не могут. Дай человеку править
весь промпт целиком — и первая же правка сломает разбор, причём молча.

**Разбираем по `id`, а не по порядку.** Модель охотно меняет порядок и
пропускает строки; позиционное сопоставление в этом случае не ошибается — оно
приземляет перевод на чужой ключ, что гораздо хуже.

**Не разобралось — переспрашиваем, потом идём по одной.** И только та строка,
что не далась и поодиночке, возвращается как `None`. Ронять из-за неё пачку в
полсотни строк расточительно.
"""
from __future__ import annotations

import json
import re

from pdxloc.core.mt_errors import MtResponseError

# Схема ответа для провайдеров, умеющих структурированный вывод. Там, где она
# поддерживается, разбирать становится почти нечего: сервис сам гарантирует
# форму, и деградация до запроса по строке остаётся редким путём, а не обычным.
# Верхний уровень — объект, а не массив: этого требуют оба сервиса.
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
    "You translate strings from a Crusader Kings III mod.\n"
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

# Модель любит обернуть ответ в ```json … ``` — снимаем, не мешая остальному.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
_ARRAY_RE = re.compile(r"\[.*\]", re.S)


def build_prompt(guidance: str, src_locale: str, tgt_locale: str) -> str:
    """Договор плюс пожелания пользователя — именно в таком порядке."""
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
    """Разобрать ответ в {номер: перевод}. Что не разобралось — просто нет.

    Ошибку не возбуждаем: решение, что делать с недостачей, принимает
    `translate_with_fallback` — он умеет переспросить.
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
    # Со структурированным выводом приходит {"rows": [...]}, без него модель
    # с равным успехом отдаёт голый массив. Принимаем обе формы.
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
    """Один заход. Нечитаемый ответ — это «ничего не разобралось», не крах.

    Ловим только `MtResponseError`: нечитаемый ответ и отказ на пачке лечатся
    повтором и разбивкой, а неверный ключ, исчерпанная квота и отсутствие сети
    — нет. Пойди мы дробить пачку при неверном ключе, получили бы полсотни
    бессмысленных запросов вместо одного внятного отказа.
    """
    try:
        return parse_answer(ask(chunk), expected)
    except MtResponseError:
        return {}


def translate_with_fallback(ask, texts: list[str]) -> list[str | None]:
    """Спросить пачкой, потом ещё раз, потом по одной.

    `ask(list[str]) -> str` — сырой ответ модели на переданные строки.

    Разбивка нужна не только на случай оборванного ответа: сервис способен
    отказаться переводить пачку целиком из-за одной строки в ней. Пятьдесят
    строк, потерянных из-за одной, — не та цена, которую стоит платить.
    """
    answers = _attempt(ask, texts, len(texts))
    missing = [i for i in range(len(texts)) if i not in answers]

    if missing and len(texts) > 1:
        # Второй заход целиком: чаще всего модель просто оборвала ответ, и
        # повтор обходится дешевле, чем полсотни запросов по одному.
        for index, value in _attempt(ask, texts, len(texts)).items():
            answers.setdefault(index, value)
        missing = [i for i in range(len(texts)) if i not in answers]

    for index in missing:
        single = _attempt(ask, [texts[index]], 1)
        if 0 in single:
            answers[index] = single[0]

    return [answers.get(i) for i in range(len(texts))]

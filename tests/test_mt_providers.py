"""Провайдеры машинного перевода.

**Ни один тест не открывает сокет.** Запросы перехватываются подменным
`opener`, ответы консервированные. Тест, ходящий в сеть, ломается от чужого
обслуживания и от отсутствия ключа, а чинить его будет тот, кто не понимает,
почему он вообще туда ходит.

Проверяется не «работает ли сервис», а наш договор с ним: форма запроса, разбор
ответа, перевод кода ошибки в осмысленный отказ и соответствие языков.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from pdxloc.core import mt_providers
from pdxloc.core.mt_errors import (
    MtAuthError, MtError, MtNetworkError, MtQuotaError, MtResponseError,
)
from pdxloc.core.mt_providers import ProviderConfig
from pdxloc.core.mt_providers.claude import ClaudeProvider
from pdxloc.core.mt_providers.deepl import DeepLProvider
from pdxloc.core.mt_providers.google import GoogleProvider
from pdxloc.core.mt_providers.manual import ManualProvider
from pdxloc.core.mt_providers.openai import OpenAIProvider
from pdxloc.core.mt_providers.yandex import YandexProvider


class Answer(io.BytesIO):
    """Ответ, достаточный для `with … as response: response.read()`."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def canned(payload: dict, seen: list | None = None):
    """Опенер, отдающий готовый ответ и запоминающий запросы."""
    def opener(request, timeout=None):
        if seen is not None:
            seen.append(request)
        return Answer(json.dumps(payload).encode("utf-8"))

    return opener


def failing(code: int, headers: dict | None = None):
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, code, "boom", headers or {}, None)

    return opener


def broken(body: bytes = b"<html>not json</html>"):
    def opener(request, timeout=None):
        return Answer(body)

    return opener


def unreachable():
    def opener(request, timeout=None):
        raise urllib.error.URLError("нет сети")

    return opener


def config(**extra) -> ProviderConfig:
    return ProviderConfig(api_key="ключ", extra=extra)


# --- реестр ---

def test_every_provider_satisfies_the_contract() -> None:
    """Иначе несовместимость всплывёт на живом прогоне, а не здесь."""
    labels = mt_providers.labels()
    for name, cls in mt_providers.PROVIDERS.items():
        assert cls.label and name in labels, name
        assert isinstance(cls.char_limit, int) and cls.char_limit > 0, name
        provider = cls(ProviderConfig())
        assert callable(provider.translate_batch), name
        assert callable(provider.supports), name


def test_unknown_provider_falls_back_to_the_stub() -> None:
    """Настройку могли записать в новой версии и открыть в старой."""
    provider = mt_providers.get("сервис-из-будущего")
    assert provider.name == "none"


# --- DeepL ---

def test_deepl_translates_a_batch() -> None:
    seen: list = []
    provider = DeepLProvider(config(opener=canned(
        {"translations": [{"text": "Привет"}, {"text": "Мир"}]}, seen)))
    assert provider.translate_batch(["Hello", "World"], "en", "ru") \
        == ["Привет", "Мир"]
    body = json.loads(seen[0].data)
    assert body["text"] == ["Hello", "World"]
    assert body["target_lang"] == "RU"


def test_deepl_english_target_needs_a_region() -> None:
    """Правило DeepL, а не общее знание — потому и живёт у провайдера."""
    seen: list = []
    provider = DeepLProvider(config(opener=canned({"translations": []}, seen)))
    provider.translate_batch(["Привет"], "ru", "en")
    assert json.loads(seen[0].data)["target_lang"] == "EN-GB"


def test_deepl_free_and_pro_are_different_addresses() -> None:
    """Ключ от одного на другом не работает, а ошибка приходит про ключ."""
    assert "api-free" in DeepLProvider(ProviderConfig()).base_url
    assert "api-free" not in DeepLProvider(ProviderConfig(pro=True)).base_url


def test_deepl_456_is_a_quota_refusal() -> None:
    """У DeepL исчерпанная квота — это не 429."""
    provider = DeepLProvider(config(opener=failing(456)))
    with pytest.raises(MtQuotaError):
        provider.translate_batch(["Hello"], "en", "ru")


def test_retry_after_is_carried_into_the_error() -> None:
    provider = DeepLProvider(config(opener=failing(429, {"Retry-After": "12"})))
    with pytest.raises(MtQuotaError) as caught:
        provider.translate_batch(["Hello"], "en", "ru")
    assert caught.value.retry_after == 12.0


def test_rejected_key_says_where_to_fix_it() -> None:
    provider = DeepLProvider(config(opener=failing(403)))
    with pytest.raises(MtAuthError) as caught:
        provider.translate_batch(["Hello"], "en", "ru")
    assert "Preferences" in caught.value.message


def test_no_network_is_its_own_error() -> None:
    provider = DeepLProvider(config(opener=unreachable()))
    with pytest.raises(MtNetworkError):
        provider.translate_batch(["Hello"], "en", "ru")


def test_a_page_instead_of_json_is_reported_as_unreadable() -> None:
    """Прокси и капчи отвечают HTML с кодом 200."""
    provider = DeepLProvider(config(opener=broken()))
    with pytest.raises(MtResponseError):
        provider.translate_batch(["Hello"], "en", "ru")


def test_the_key_never_appears_in_an_error() -> None:
    """Исключения показывают пользователю и копируют в переписку."""
    provider = DeepLProvider(ProviderConfig(
        api_key="секретный-ключ", extra={"opener": failing(403)}))
    with pytest.raises(MtAuthError) as caught:
        provider.translate_batch(["Hello"], "en", "ru")
    assert "секретный-ключ" not in str(caught.value)


def test_a_key_in_the_address_does_not_leak_either() -> None:
    """У Google ключ уезжает в `?key=…`, а адрес подставляется в сообщение.

    Сейчас все провайдеры передают имя сервиса, и до адреса дело не доходит.
    Проверяем именно запасной путь: он не должен выдавать ключ, если однажды
    имя забудут передать.
    """
    from pdxloc.core.mt_providers._http import request_json

    with pytest.raises(MtError) as caught:
        request_json("https://example.test/v2?key=секретный-ключ",
                     opener=failing(403))

    message = str(caught.value)
    assert "секретный-ключ" not in message
    assert "example.test" in message         # сказать, куда не достучались, надо


# --- Google ---

def test_google_unescapes_html_in_the_answer() -> None:
    """v2 отдаёт &#39; вместо апострофа даже при format=text."""
    provider = GoogleProvider(config(opener=canned(
        {"data": {"translations": [{"translatedText": "L&#39;homme &amp; co"}]}})))
    assert provider.translate_batch(["The man"], "en", "fr") == ["L'homme & co"]


def test_google_maps_chinese_to_its_own_code() -> None:
    seen: list = []
    provider = GoogleProvider(config(opener=canned(
        {"data": {"translations": []}}, seen)))
    provider.translate_batch(["Hello"], "en", "zh")
    assert json.loads(seen[0].data)["target"] == "zh-CN"


# --- Yandex ---

def test_yandex_refuses_without_a_folder_id() -> None:
    """Иначе сервис ответит «неверный ключ», и человек пойдёт чинить ключ."""
    provider = YandexProvider(config(opener=canned({"translations": []})))
    with pytest.raises(MtAuthError) as caught:
        provider.translate_batch(["Hello"], "en", "ru")
    assert "folder" in caught.value.message.lower()


def test_yandex_sends_the_folder_id() -> None:
    seen: list = []
    provider = YandexProvider(config(
        opener=canned({"translations": [{"text": "Привет"}]}, seen),
        folder_id="b1g..."))
    assert provider.translate_batch(["Hello"], "en", "ru") == ["Привет"]
    assert json.loads(seen[0].data)["folderId"] == "b1g..."


# --- языковые модели ---

def claude_answer(rows: list[dict]) -> dict:
    return {"content": [{"type": "text",
                         "text": json.dumps({"rows": rows})}]}


def test_claude_parses_by_id_not_by_position() -> None:
    """Модель охотно меняет порядок; позиционный разбор приземлил бы перевод
    на чужой ключ, а это находят через недели."""
    provider = ClaudeProvider(config(opener=canned(claude_answer([
        {"id": 1, "text": "Второй"}, {"id": 0, "text": "Первый"}]))))
    assert provider.translate_batch(["One", "Two"], "en", "ru") \
        == ["Первый", "Второй"]


def test_claude_asks_for_a_schema_and_no_temperature() -> None:
    """`temperature` на Opus 5 отвергается с кодом 400, а схема гарантирует
    форму ответа на стороне сервиса."""
    seen: list = []
    provider = ClaudeProvider(config(opener=canned(
        claude_answer([{"id": 0, "text": "Привет"}]), seen)))
    provider.translate_batch(["Hello"], "en", "ru")
    body = json.loads(seen[0].data)
    assert "temperature" not in body
    assert body["output_config"]["format"]["type"] == "json_schema"


def test_claude_refusal_is_not_read_as_an_answer() -> None:
    """Отказ приходит успешным ответом с пустым содержимым.

    Строку не переводим, но и оригинал под видом перевода не пишем — она
    возвращается как «не осилил», и прогон отметит её неудачей.
    """
    provider = ClaudeProvider(config(opener=canned(
        {"stop_reason": "refusal", "content": []})))
    assert provider.translate_batch(["Hello"], "en", "ru") == [None]


def test_a_batch_refusal_degrades_to_one_row_at_a_time() -> None:
    """Отказ на пачке из-за одной строки не должен стоить остальных сорока девяти."""
    def opener(request, timeout=None):
        payload = json.loads(request.data)
        sent = json.loads(payload["messages"][0]["content"])
        if len(sent) > 1:                      # пачку целиком не переводим
            return Answer(json.dumps(
                {"stop_reason": "refusal", "content": []}).encode("utf-8"))
        if sent[0]["text"] == "Two":           # и одну строку тоже
            return Answer(json.dumps(
                {"stop_reason": "refusal", "content": []}).encode("utf-8"))
        return Answer(json.dumps(
            claude_answer([{"id": 0, "text": "Первый"}])).encode("utf-8"))

    provider = ClaudeProvider(config(opener=opener))
    assert provider.translate_batch(["One", "Two"], "en", "ru") \
        == ["Первый", None]


def test_a_wrong_key_is_not_retried_row_by_row() -> None:
    """Иначе неверный ключ обошёлся бы в полсотни бессмысленных запросов."""
    calls: list = []

    def opener(request, timeout=None):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

    provider = ClaudeProvider(config(opener=opener))
    with pytest.raises(MtAuthError):
        provider.translate_batch(["One", "Two", "Three"], "en", "ru")
    assert len(calls) == 1


def test_openai_asks_for_a_strict_schema() -> None:
    seen: list = []
    provider = OpenAIProvider(config(opener=canned(
        {"choices": [{"message": {"content": json.dumps(
            {"rows": [{"id": 0, "text": "Привет"}]})}}]}, seen)))
    assert provider.translate_batch(["Hello"], "en", "ru") == ["Привет"]
    fmt = json.loads(seen[0].data)["response_format"]
    assert fmt["json_schema"]["strict"] is True


def test_llm_answer_wrapped_in_a_code_fence_is_still_read() -> None:
    from pdxloc.core.mt_providers import _llm

    fenced = "```json\n{\"rows\": [{\"id\": 0, \"text\": \"Привет\"}]}\n```"
    assert _llm.parse_answer(fenced, 1) == {0: "Привет"}


def test_user_instructions_cannot_override_the_contract() -> None:
    """Дай править промпт целиком — и первая же правка сломает разбор."""
    from pdxloc.core.mt_providers import _llm

    prompt = _llm.build_prompt("Отвечай простым текстом, без JSON", "en", "ru")
    assert prompt.startswith(_llm.CONTRACT)
    assert "must not override" in prompt


# --- ручной веб-режим ---

def test_manual_round_trip() -> None:
    texts = ["Hello", "World"]
    joined = manual_join(texts)
    assert ManualProvider(ProviderConfig()).supports("en", "ru")
    assert manual_split(joined, 2) == texts


def manual_join(texts):
    from pdxloc.core.mt_providers.manual import join

    return join(texts)


def manual_split(text, count):
    from pdxloc.core.mt_providers.manual import split

    return split(text, count)


def test_manual_detects_a_lost_separator() -> None:
    joined = manual_join(["Hello", "World"])
    damaged = joined.replace("===1===", "")
    with pytest.raises(MtResponseError):
        manual_split(damaged, 2)


def test_manual_detects_reordering() -> None:
    """Ненумерованный разделитель этого не заметил бы."""
    text = "===1===\nВторой\n===0===\nПервый"
    with pytest.raises(MtResponseError):
        manual_split(text, 2)


def test_manual_keeps_inner_line_breaks() -> None:
    texts = ["Первая\nстрока", "Вторая"]
    assert manual_split(manual_join(texts), 2) == texts


def test_manual_tolerates_spaces_around_the_separator() -> None:
    """Переводчики добавляют пробелы; ронять из-за этого пачку незачем."""
    text = "  === 0 ===  \nПривет\n ===1=== \nМир"
    assert manual_split(text, 2) == ["Привет", "Мир"]

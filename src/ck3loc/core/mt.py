"""Каркас машинного перевода.

Живых провайдеров пока нет — есть интерфейс и, главное, защита разметки CK3:
переводчики (и люди, и сервисы) охотно ломают [GetTrait('x').GetName], $VALUE$,
£gold£ и #bold …#!. Перед отправкой такие куски заменяются на короткие
непереводимые метки, после — возвращаются на место.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from ck3loc.core.qa import (
    RE_BRACKET, RE_DOLLAR, RE_FMT_CLOSE, RE_FMT_OPEN, RE_ICON, RE_NEWLINE,
)

# Порядок важен: закрывающий #! ищем раньше открывающих тегов
_PATTERNS = (RE_BRACKET, RE_DOLLAR, RE_ICON, RE_FMT_CLOSE, RE_FMT_OPEN, RE_NEWLINE)

# Метка вида ⟦12⟧: сервисы переводят её как непонятный символ и не трогают
_TOKEN_RE = re.compile(r"⟦(\d+)⟧")


def shield_tags(text: str) -> tuple[str, dict[str, str]]:
    """Заменить разметку метками. Возвращает (текст с метками, соответствие)."""
    spans: list[tuple[int, int]] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if not any(s <= m.start() < e or s < m.end() <= e for s, e in spans):
                spans.append((m.start(), m.end()))
    spans.sort()

    mapping: dict[str, str] = {}
    out: list[str] = []
    last = 0
    for start, end in spans:
        token = f"⟦{len(mapping)}⟧"
        mapping[token] = text[start:end]
        out.append(text[last:start])
        out.append(token)
        last = end
    out.append(text[last:])
    return "".join(out), mapping


def unshield(text: str, mapping: dict[str, str]) -> str:
    """Вернуть разметку на место. Метки, потерявшие форму, восстанавливаются
    по номеру — переводчики любят вставлять пробелы внутрь скобок."""
    def replace(m: re.Match) -> str:
        return mapping.get(f"⟦{m.group(1)}⟧", m.group(0))

    restored = _TOKEN_RE.sub(replace, text)
    # запасной проход для «⟦ 3 ⟧» и подобного
    return re.sub(r"⟦\s*(\d+)\s*⟧",
                  lambda m: mapping.get(f"⟦{m.group(1)}⟧", m.group(0)), restored)


def missing_tokens(text: str, mapping: dict[str, str]) -> list[str]:
    """Метки, которые перевод потерял — сигнал, что результат сломан."""
    present = {f"⟦{m.group(1)}⟧" for m in _TOKEN_RE.finditer(text)}
    return [token for token in mapping if token not in present]


@runtime_checkable
class TranslationProvider(Protocol):
    """Провайдер машинного перевода.

    Реализация получает уже защищённые тексты и обязана вернуть столько же
    строк в том же порядке.
    """

    name: str

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str) -> list[str]:
        ...


class NoneProvider:
    """Заглушка: перевода нет. Позволяет собрать конвейер целиком."""

    name = "none"

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str) -> list[str]:
        return list(texts)


PROVIDERS: dict[str, type] = {"none": NoneProvider}

PROVIDER_LABELS = {
    "none": "Отключён",
    "deepl": "DeepL",
    "claude": "Claude API",
}


def get_provider(name: str) -> TranslationProvider:
    factory = PROVIDERS.get(name) or NoneProvider
    return factory()


def translate_texts(
    provider: TranslationProvider,
    texts: list[str],
    src_lang: str,
    tgt_lang: str,
) -> list[tuple[str, list[str]]]:
    """Перевести тексты, сохранив разметку.

    Возвращает пары (перевод, потерянные метки) — вторые заполнены, если
    провайдер испортил разметку и результат нужно проверить руками.
    """
    shielded, mappings = [], []
    for text in texts:
        s, mapping = shield_tags(text)
        shielded.append(s)
        mappings.append(mapping)

    translated = provider.translate_batch(shielded, src_lang, tgt_lang)
    if len(translated) != len(texts):
        raise RuntimeError(
            f"Провайдер вернул {len(translated)} строк вместо {len(texts)}")

    result = []
    for raw, mapping in zip(translated, mappings):
        result.append((unshield(raw, mapping), missing_tokens(raw, mapping)))
    return result


# --- настройки ---

def get_settings() -> tuple[str, str]:
    """(имя провайдера, ключ доступа) из настроек приложения."""
    from ck3loc import settings

    s = settings.qsettings()
    return str(s.value("mt/provider", "none")), str(s.value("mt/api_key", "") or "")


def save_settings(provider: str, api_key: str) -> None:
    from ck3loc import settings

    s = settings.qsettings()
    s.setValue("mt/provider", provider)
    s.setValue("mt/api_key", api_key)

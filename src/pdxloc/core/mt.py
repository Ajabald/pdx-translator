"""Защита разметки CK3 при машинном переводе.

Переводчики — и сервисы, и люди — охотно ломают `[GetTrait('x').GetName]`,
`$VALUE$`, `@gold!` и `#bold …#!`. Перед отправкой такие куски заменяются
короткими непереводимыми метками, после — возвращаются на место.

Метки двух видов, и это не прихоть:

* `⟦N⟧` по умолчанию. Символы редкие, сервисы принимают их за знак препинания
  и не трогают;
* `{{N}}` для ручного режима. Там текст проходит через поле ввода браузера и
  буфер обмена, а это ровно то место, где U+27E6 корёжится или пропадает
  вовсе. `unshield` понимает обе формы всегда — восстанавливать надо и то, что
  отправляли не мы.

Провайдеры живут в `core/mt_providers/`, оркестрация прогона — в
`core/mt_run.py`. Здесь только разметка и реестр.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pdxloc.core import markup
from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_providers import PROVIDERS, ProviderConfig, get, labels

# Состав и порядок — в core/markup.py: закрывающий #! обязан искаться раньше
# открывающих тегов, а @name! — позже [ … ], иначе иконка внутри скриптового
# вызова крадёт диапазон всей скобки.
_SHIELDED = markup.shield_tokens()

# Обе формы метки, с допуском на вставленные пробелы: переводчики любят
# «⟦ 3 ⟧», а редакторы — превращать {{3}} в { {3} }.
_TOKEN_RE = re.compile(r"⟦\s*(\d+)\s*⟧|\{\s*\{\s*(\d+)\s*\}\s*\}")

UNICODE_TOKENS = "unicode"
ASCII_TOKENS = "ascii"


def _token(index: int, kind: str) -> str:
    return f"{{{{{index}}}}}" if kind == ASCII_TOKENS else f"⟦{index}⟧"


def shield_tags(text: str, kind: str = UNICODE_TOKENS) -> tuple[str, dict[str, str]]:
    """Заменить разметку метками. Возвращает (текст с метками, соответствие)."""
    mapping: dict[str, str] = {}
    out: list[str] = []
    last = 0
    for start, end in markup.spans(text, _SHIELDED):
        token = _token(len(mapping), kind)
        mapping[token] = text[start:end]
        out.append(text[last:start])
        out.append(token)
        last = end
    out.append(text[last:])
    return "".join(out), mapping


_DIGITS_RE = re.compile(r"\d+")


def _index(match: re.Match) -> str:
    """Номер метки, какой бы из двух форм она ни была."""
    return match.group(1) or match.group(2)


def _number(token: str) -> str:
    """Номер из самой метки: «⟦7⟧» и «{{7}}» — это один и тот же номер 7."""
    found = _DIGITS_RE.search(token)
    return found.group(0) if found else ""


def _by_number(mapping: dict[str, str]) -> dict[str, str]:
    """Соответствие по номеру: форму метки в ответе мы не контролируем."""
    return {_number(token): value for token, value in mapping.items()}


def unshield(text: str, mapping: dict[str, str]) -> str:
    """Вернуть разметку на место.

    Восстанавливаем **по номеру**, а не по точному виду метки: сервис мог
    вставить пробелы внутрь, а ручной режим — прислать другую форму скобок.
    Незнакомый номер оставляем как есть: выдумывать за переводчика нечего.
    """
    by_number = _by_number(mapping)
    return _TOKEN_RE.sub(lambda m: by_number.get(_index(m), m.group(0)), text)


def missing_tokens(text: str, mapping: dict[str, str]) -> list[str]:
    """Метки, которые перевод потерял — сигнал, что результат сломан."""
    present = {_index(m) for m in _TOKEN_RE.finditer(text)}
    return [token for token in mapping if _number(token) not in present]


@runtime_checkable
class TranslationProvider(Protocol):
    """Провайдер машинного перевода.

    Получает уже защищённые тексты и обязан вернуть столько же строк в том же
    порядке. Сопоставление идёт по позиции, и это единственное, на что можно
    опереться: одинаковые оригиналы в проекте — обычное дело, и искать
    соответствие по тексту значило бы их перепутать.

    Вернуть можно и `None` вместо строки — это значит «эту строку перевести не
    удалось». Поблажка понадобилась LLM: они не всегда отдают N ответов на N
    запросов, и ронять из-за одной строки пачку в полсотни было бы
    расточительно. Классические сервисы ею не пользуются.
    """

    name: str
    label: str
    char_limit: int

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        ...

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str | None]:
        ...


def get_provider(name: str, config: ProviderConfig | None = None):
    """Провайдер по имени. Неизвестное имя — заглушка (см. `mt_providers.get`)."""
    return get(name, config)


def provider_labels() -> dict[str, str]:
    return labels()


def translate_texts(
    provider: TranslationProvider,
    texts: list[str],
    src_locale: str,
    tgt_locale: str,
) -> list[tuple[str | None, list[str]]]:
    """Перевести тексты, сохранив разметку.

    Возвращает пары (перевод, потерянные метки). Перевод `None` значит, что
    провайдер эту строку не осилил; вторые заполнены, если разметка испорчена
    и результат нужно проверить руками.
    """
    shielded, mappings = [], []
    for text in texts:
        s, mapping = shield_tags(text)
        shielded.append(s)
        mappings.append(mapping)

    translated = provider.translate_batch(shielded, src_locale, tgt_locale)
    if len(translated) != len(texts):
        raise RuntimeError(
            fill(translate("Mt", "The provider returned %1 rows instead of %2"),
                 len(translated), len(texts)))

    result = []
    for raw, mapping in zip(translated, mappings, strict=True):
        if raw is None:
            result.append((None, []))
            continue
        result.append((unshield(raw, mapping), missing_tokens(raw, mapping)))
    return result


# --- ключи доступа ---
#
# Ключи лежат не в `gui/prefs.py`, и это не мелочь. `prefs.get` отдал бы
# защищённую строку вместо ключа, а `prefs.notifier` рассылал бы сигнал
# «настройка изменилась» на каждое нажатие клавиши в поле ввода. Ключей к тому
# же по одному на провайдера, а `prefs.DEFAULTS` требует знать имя на импорте.
# Поэтому — рядом с `bdd_dir` и списком недавних проектов, через `settings`.

_KEY_PREFIX = "mt/key/"


def api_key(provider: str) -> str:
    """Ключ провайдера в открытом виде — только чтобы отдать его в запрос."""
    from pdxloc import settings
    from pdxloc.core import secrets

    stored = str(settings.qsettings().value(f"{_KEY_PREFIX}{provider}", "") or "")
    return secrets.unprotect(stored)


def save_api_key(provider: str, key: str) -> None:
    from pdxloc import settings
    from pdxloc.core import secrets

    settings.qsettings().setValue(
        f"{_KEY_PREFIX}{provider}", secrets.protect(key.strip()))


def forget_api_key(provider: str) -> None:
    from pdxloc import settings

    settings.qsettings().setValue(f"{_KEY_PREFIX}{provider}", "")


def key_is_protected(provider: str) -> bool:
    """Защищён ли ключ системой. «Параметры» обязаны показывать правду."""
    from pdxloc import settings
    from pdxloc.core import secrets

    stored = str(settings.qsettings().value(f"{_KEY_PREFIX}{provider}", "") or "")
    return secrets.is_protected(stored)


__all__ = [
    "ASCII_TOKENS", "PROVIDERS", "ProviderConfig", "TranslationProvider",
    "UNICODE_TOKENS", "api_key", "forget_api_key", "get_provider",
    "key_is_protected", "missing_tokens", "provider_labels", "save_api_key",
    "shield_tags", "translate_texts", "unshield",
]

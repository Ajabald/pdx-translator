"""Провайдеры машинного перевода: реестр и общий договор.

По файлу на сервис. Каждый описывает только своё: адрес, заголовок с ключом,
форму запроса и ответа, свои коды ошибок и **своё соответствие языков**.
Последнее живёт у провайдера намеренно: `EN-GB` и `PT-BR` — правило DeepL, а не
общее знание, и единая матрица «язык × сервис» протухла бы на первом же
изменении чужого API, оставшись при этом единственным местом, куда никто не
заглядывает.

Настройки провайдер не читает: он получает готовый `ProviderConfig`. Иначе
`core/` потянул бы за собой `settings`, а с ним и Qt, — а ядро обязано
импортироваться без PySide6 (см. `tests/test_i18n.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pdxloc.core.i18n import QT_TRANSLATE_NOOP


@dataclass(frozen=True)
class ProviderConfig:
    """Всё, что провайдеру нужно знать снаружи.

    Собирается вызывающей стороной (интерфейсом), а не читается из настроек:
    так провайдер остаётся проверяемым без окружения и без Qt.
    """

    api_key: str = ""
    pro: bool = False                # у DeepL это другой адрес, не тариф
    model: str = ""                  # для LLM; пусто — умолчание провайдера
    prompt: str = ""                 # пожелания пользователя к LLM, не договор
    extra: dict[str, str] = field(default_factory=dict)   # напр. folder_id Yandex
    timeout: float = 30.0


class NoneProvider:
    """Заглушка: перевода нет, текст возвращается как есть.

    Нужна не только для тестов. С ней конвейер — охват, пачки, статусы, откат,
    сводка — проверяется целиком и на живом проекте, не тратя ни запроса.
    """

    name = "none"
    label = QT_TRANSLATE_NOOP("Mt", "Off")
    char_limit = 1_000_000
    needs_key = False

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return True

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str]:
        return list(texts)


# Имя -> класс; порядок здесь определяет порядок в списке «Параметров».
# Заполняется лениво: модули провайдеров импортируют этот же файл ради
# `ProviderConfig`, и собрать словарь на месте значило бы завести цикл.
PROVIDERS: dict[str, type] = {
    NoneProvider.name: NoneProvider,
}

_LOADED = False


def _load() -> None:
    """Подтянуть провайдеров при первом обращении."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from pdxloc.core.mt_providers.claude import ClaudeProvider
    from pdxloc.core.mt_providers.deepl import DeepLProvider
    from pdxloc.core.mt_providers.google import GoogleProvider
    from pdxloc.core.mt_providers.manual import ManualProvider
    from pdxloc.core.mt_providers.openai import OpenAIProvider
    from pdxloc.core.mt_providers.yandex import YandexProvider

    for cls in (DeepLProvider, ClaudeProvider, OpenAIProvider,
                GoogleProvider, YandexProvider, ManualProvider):
        PROVIDERS.setdefault(cls.name, cls)


def labels() -> dict[str, str]:
    """Имя -> подпись для интерфейса (ещё не переведённая)."""
    _load()
    return {name: cls.label for name, cls in PROVIDERS.items()}


def get(name: str, config: ProviderConfig | None = None):
    """Провайдер по имени. Неизвестное имя — заглушка, а не исключение.

    Настройку могли записать в новой версии и открыть в старой; молча
    переводить нечем — но и падать при открытии проекта не за что.
    """
    _load()
    factory = PROVIDERS.get(name) or NoneProvider
    return factory(config or ProviderConfig())

"""Диагностический лог: единственный ответ на «оно упало».

Публичный релиз — это чужие машины, к которым не подойти. Без лога на жалобу
«не работает» сказать нечего: воспроизвести чужой мод, чужую игру и чужой
Windows нельзя, а трассировка приходит одним файлом.

Три решения, каждое со своей причиной:

* **файл рядом с приложением**, а не в `%APPDATA%`. Приложение переносимое —
  живёт хоть на флешке, — и лог должен уезжать вместе с ним. `app_root()` уже
  умеет отличать сборку от исходников;
* **`RotatingFileHandler` из стандартной библиотеки**. Единственная зависимость
  этого проекта — PySide6, и заводить вторую ради записи в файл не станем. Без
  ротации файл рос бы вечно на машине, куда никто не заглядывает;
* **`sys.excepthook`**. Ради него всё и делается: необработанное исключение в
  Qt-приложении сейчас уходит в никуда — окно продолжает стоять, человек видит
  «ничего не произошло», и рассказать об этом ему нечем.

Модуль **не импортирует Qt**: `--scan-cli` работает без PySide6 и обязан
продолжать, а лог нужен ему ровно так же.
"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
from pathlib import Path

LOG_NAME = "pdx-translator.log"

# Мегабайта хватает на несколько сеансов с трассировками, а две копии позволяют
# спросить «а что было в прошлый раз» — обычно ломается не с первого запуска.
MAX_BYTES = 1_000_000
BACKUPS = 2

_configured = False


def log_path() -> Path:
    from pdxloc import settings

    return settings.app_root() / LOG_NAME


def setup(*, level: int = logging.INFO) -> Path | None:
    """Завести файловый лог и перехват необработанных исключений.

    Возвращает путь к файлу или None, если писать не удалось. **Молчаливый
    отказ здесь намеренный**: приложение, которое не запускается из-за того,
    что не смогло завести лог, — хуже приложения без лога. Каталог бывает
    только на чтение (флешка с защитой, `Program Files` без прав), и это не
    повод не работать.
    """
    global _configured
    if _configured:
        return log_path()

    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError:
        return None

    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True

    sys.excepthook = _log_uncaught
    _log_environment()
    return path


def _log_environment() -> None:
    """Три строки, снимающие половину вопросов ещё до чтения трассировки."""
    from pdxloc import __version__

    log = logging.getLogger("pdxloc")
    log.info("PDX Translator %s", __version__)
    log.info("Python %s", sys.version.replace("\n", " "))
    log.info("%s %s", platform.system(), platform.release())
    log.info("frozen=%s root=%s", getattr(sys, "frozen", False), log_path().parent)


def _log_uncaught(exc_type, exc, tb) -> None:
    """Записать необработанное исключение и отдать его прежнему обработчику.

    Прежний зовётся обязательно: без него исчезнет привычный вывод в консоль
    при запуске из исходников, а `KeyboardInterrupt` перестанет выглядеть
    прерыванием.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("pdxloc").critical(
        "Необработанное исключение", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)

"""Хранение ключей доступа: DPAPI там, где он есть.

Ключи к сервисам перевода лежат в настройках приложения, то есть в реестре
Windows. Открытым текстом это значит, что ключ виден всякому, кто откроет
`regedit` через плечо, и уезжает вместе со скопированным кустом реестра.

`CryptProtectData` шифрует данные на учётной записи Windows. Что это даёт и
чего не даёт, стоит назвать честно, потому что подсказка в интерфейсе обязана
говорить то же самое:

* **защищает** от чужих глаз в реестре и от переноса куста на другую машину;
* **не защищает** от программы, запущенной под тем же пользователем. Такая
  программа расшифрует ключ тем же вызовом.

Отсюда формулировка «защищён Windows для вашей учётной записи», а не
«зашифрован».

`ctypes`, а не новая зависимость — тем же приёмом и по той же причине, что
`core/trash.py`. Где DPAPI недоступен (не Windows) или отказал, возвращаем
текст как есть и **сообщаем об этом**: молчаливый откат научил бы считать
открытый ключ защищённым.
"""
from __future__ import annotations

import base64
import sys

_PREFIX = "dpapi:"      # чем помечен защищённый ключ в хранилище


def available() -> bool:
    """Умеет ли система защищать данные на учётной записи."""
    return sys.platform == "win32"


def _blob():
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    return ctypes, DATA_BLOB


def protect(plain: str) -> str:
    """Защитить ключ. Возвращает строку для хранения.

    Не вышло — возвращаем открытый текст: потерять ключ пользователя хуже, чем
    сохранить его незащищённым, о чём интерфейс и скажет (`is_protected`).
    """
    if not plain or not available():
        return plain
    try:
        ctypes, DATA_BLOB = _blob()
        raw = plain.encode("utf-8")
        source = DATA_BLOB(len(raw), ctypes.cast(
            ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        result = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result))
        if not ok:
            return plain
        try:
            data = ctypes.string_at(result.pbData, result.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(result.pbData)
        return _PREFIX + base64.b64encode(data).decode("ascii")
    except (AttributeError, OSError, ValueError):
        return plain


def unprotect(stored: str) -> str:
    """Прочитать ключ. Незащищённый возвращается как есть.

    Испорченный или чужой (перенесённый с другой машины) блоб — это не ключ;
    возвращаем пусто, чтобы интерфейс попросил ввести заново, а не отправлял
    мусор в сервис.
    """
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        return stored
    if not available():
        return ""
    try:
        ctypes, DATA_BLOB = _blob()
        raw = base64.b64decode(stored[len(_PREFIX):])
        source = DATA_BLOB(len(raw), ctypes.cast(
            ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        result = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result))
        if not ok:
            return ""
        try:
            data = ctypes.string_at(result.pbData, result.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(result.pbData)
        return data.decode("utf-8")
    except (AttributeError, OSError, ValueError, UnicodeDecodeError):
        return ""


def is_protected(stored: str) -> bool:
    """Лежит ли ключ защищённым. Нужно подсказке в «Параметрах»."""
    return bool(stored) and stored.startswith(_PREFIX)

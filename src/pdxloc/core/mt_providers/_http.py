"""HTTP поверх стандартной библиотеки: один запрос и разбор кода ответа.

`urllib.request`, а не `requests`: единственная зависимость приложения —
PySide6, и заводить вторую ради нескольких POST-запросов не стоит. `QtNetwork`
тоже не подходит — он сигнальный, а вся тяжёлая работа идёт в потоке-воркере
обычным синхронным циклом.

Здесь единственное место, где код ответа превращается в осмысленную ошибку.
Коды передаёт провайдер: у DeepL исчерпанная квота приходит как 456, у Google
как 403 с причиной в теле, и общей таблицей это не описать.

Ни ключ, ни тело запроса в сообщения не попадают.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping

from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import (
    MtAuthError, MtNetworkError, MtQuotaError, MtResponseError,
)

DEFAULT_TIMEOUT = 30.0

# Ответ длиннее этого читать незачем: у всех провайдеров это уже не перевод,
# а страница от прокси или капча.
_MAX_BODY = 8 * 1024 * 1024

AUTH_CODES = (401, 403)
QUOTA_CODES = (429,)


def request_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    method: str = "POST",
    timeout: float = DEFAULT_TIMEOUT,
    service: str = "",
    auth_codes: tuple[int, ...] = AUTH_CODES,
    quota_codes: tuple[int, ...] = QUOTA_CODES,
    opener=None,
) -> dict:
    """Сделать запрос и вернуть разобранный JSON.

    `service` — имя сервиса для сообщений. `opener` подменяется в тестах:
    ни один тест не открывает сокет.
    """
    request = urllib.request.Request(
        url, data=data, headers=dict(headers or {}), method=method)
    do_open = opener or urllib.request.urlopen
    named = service or _without_query(url)

    try:
        with do_open(request, timeout=timeout) as response:
            body = response.read(_MAX_BODY)
    except urllib.error.HTTPError as error:
        raise _from_status(error, named, auth_codes, quota_codes) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise MtNetworkError(
            fill(translate("Mt", "Could not reach %1: %2"),
                 named, _reason(error))) from None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _unreadable(named) from None
    if not isinstance(parsed, dict):
        raise _unreadable(named)
    return parsed


def _without_query(url: str) -> str:
    """Адрес без параметров: у Google ключ уезжает именно в `?key=…`.

    Все провайдеры передают `service`, и до подстановки адреса дело не доходит.
    Но обещание «ключ не попадает в сообщения» не должно держаться на том, что
    каждый следующий вызов не забудет про имя сервиса: сообщение об ошибке
    человек копирует в переписку целиком.
    """
    return url.split("?", 1)[0]


def _from_status(
    error: urllib.error.HTTPError,
    service: str,
    auth_codes: tuple[int, ...],
    quota_codes: tuple[int, ...],
) -> Exception:
    # Квота проверяется первой: у Google исчерпанный лимит приходит тем же 403,
    # что и неверный ключ, и провайдер разводит их, передав свои коды.
    if error.code in quota_codes:
        return MtQuotaError(
            fill(translate("Mt", "%1 refused: the request limit or the quota "
                                 "is exhausted."), service),
            _retry_after(getattr(error, "headers", None)))
    if error.code in auth_codes:
        return MtAuthError(
            fill(translate("Mt", "%1 rejected the key. Check it in "
                                 "«File → Preferences → Machine translation»."),
                 service))
    return MtResponseError(
        fill(translate("Mt", "%1 answered with an error (code %2)."),
             service, error.code))


def _unreadable(service: str) -> MtResponseError:
    return MtResponseError(
        fill(translate("Mt", "%1 returned an answer that could not be read."),
             service))


def _retry_after(headers) -> float | None:
    raw = headers.get("Retry-After") if headers else None
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None      # бывает дата в формате HTTP — тогда ждём по-своему


def _reason(error: Exception) -> str:
    reason = getattr(error, "reason", None)
    return str(reason) if reason else error.__class__.__name__

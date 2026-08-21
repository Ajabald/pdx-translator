"""HTTP on the standard library: one request and the reading of its status.

`urllib.request` rather than `requests`: the application has one dependency,
PySide6, and a second is not worth a handful of POST requests. `QtNetwork` does
not fit either — it is signal-driven, while all the heavy work runs in a worker
thread as a plain synchronous loop.

This is the single place where a status code turns into a meaningful error. The
codes come from the provider: with DeepL an exhausted quota arrives as 456, with
Google as a 403 carrying the reason in the body, and no shared table describes
that.

Neither the key nor the request body ever reaches a message.
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

# Reading an answer longer than this is pointless: with every provider it is
# no longer a translation but a proxy page or a captcha.
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
    """Make the request and return the parsed JSON.

    `service` is the service name used in messages. `opener` is replaced in the
    tests: not one test opens a socket.
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
    """The address without its query: with Google the key rides in `?key=…`.

    Every provider passes `service`, so it never comes to falling back on the
    address. But the promise that «the key never reaches a message» must not rest
    on every future call remembering the service name: people paste an error
    message into a chat whole.
    """
    return url.split("?", 1)[0]


def _from_status(
    error: urllib.error.HTTPError,
    service: str,
    auth_codes: tuple[int, ...],
    quota_codes: tuple[int, ...],
) -> Exception:
    # The quota is checked first: with Google an exhausted limit arrives as the
    # same 403 as a bad key, and the provider tells them apart by passing its own
    # codes.
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
        return None      # sometimes an HTTP-format date; then we work it out ourselves


def _reason(error: Exception) -> str:
    reason = getattr(error, "reason", None)
    return str(reason) if reason else error.__class__.__name__

"""Storing access keys: DPAPI wherever it exists.

Keys to the translation services live in the application settings, which on
Windows means the registry. In plain text that means the key is visible to anyone
who opens `regedit` over your shoulder, and it travels with a copied hive.

`CryptProtectData` encrypts data against the Windows account. What that gives and
what it does not is worth naming honestly, because the hint in the interface has
to say the same thing:

* it **protects** against other eyes in the registry and against the hive being
  carried to another machine;
* it does **not protect** against a program running under the same user. Such a
  program decrypts the key with the same call.

Hence the wording «protected by Windows for your account» rather than
«encrypted».

`ctypes` instead of a new dependency, by the same trick and for the same reason
as `core/trash.py`. Where DPAPI is unavailable (not Windows) or refuses, the text
is returned as it is and **we say so**: a silent fallback would teach people to
consider a plain key protected.
"""
from __future__ import annotations

import base64
import sys

_PREFIX = "dpapi:"      # how a protected key is marked in the store


def available() -> bool:
    """Whether the system can protect data against the account."""
    return sys.platform == "win32"


def _blob():
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    return ctypes, DATA_BLOB


def protect(plain: str) -> str:
    """Protect a key. Returns the string to store.

    If it did not work we return plain text: losing the user's key is worse than
    storing it unprotected, and the interface says so (`is_protected`).
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
    """Read a key. An unprotected one is returned as it is.

    A corrupted or foreign blob — one carried over from another machine — is not
    a key; we return nothing, so the interface asks for it again instead of
    sending rubbish to the service.
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
    """Whether the stored key is protected. The hint in «Preferences» needs it."""
    return bool(stored) and stored.startswith(_PREFIX)

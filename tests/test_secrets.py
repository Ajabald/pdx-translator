"""Хранение ключей доступа.

Проверяется не стойкость шифрования — её обеспечивает система, — а то, что
инструмент **не врёт о состоянии ключа**. Открытый ключ, показанный как
защищённый, хуже открытого ключа, показанного честно: во втором случае человек
хотя бы знает, где он лежит.
"""
from __future__ import annotations

import sys

import pytest

from pdxloc.core import secrets


@pytest.mark.skipif(not secrets.available(), reason="DPAPI есть только в Windows")
def test_key_round_trips_through_the_system() -> None:
    protected = secrets.protect("sk-секрет-123")
    assert protected != "sk-секрет-123"
    assert secrets.unprotect(protected) == "sk-секрет-123"


@pytest.mark.skipif(not secrets.available(), reason="DPAPI есть только в Windows")
def test_protected_key_is_marked_as_such() -> None:
    assert secrets.is_protected(secrets.protect("ключ"))
    assert not secrets.is_protected("ключ")
    assert not secrets.is_protected("")


def test_empty_key_stays_empty() -> None:
    assert secrets.protect("") == ""
    assert secrets.unprotect("") == ""


def test_plain_text_is_returned_as_is() -> None:
    """Ключи, записанные прежней версией, читаются без потерь."""
    assert secrets.unprotect("sk-старый-ключ") == "sk-старый-ключ"


def test_a_broken_blob_yields_nothing(monkeypatch) -> None:
    """Испорченный или чужой блоб — это не ключ.

    Вернуть мусор значило бы отправить его в сервис и получить непонятную
    ошибку авторизации вместо внятного «введите ключ заново».
    """
    assert secrets.unprotect("dpapi:не-base64-вовсе") == ""
    assert secrets.unprotect("dpapi:" + "AAAA") == ""


@pytest.mark.skipif(sys.platform == "win32", reason="проверяем поведение без DPAPI")
def test_without_dpapi_the_key_is_stored_plainly() -> None:
    assert secrets.protect("ключ") == "ключ"
    assert not secrets.is_protected("ключ")


def test_failure_falls_back_instead_of_losing_the_key(monkeypatch) -> None:
    """Потерять ключ пользователя хуже, чем сохранить его незащищённым."""
    monkeypatch.setattr(secrets, "available", lambda: True)
    monkeypatch.setattr(secrets, "_blob", lambda: (_ for _ in ()).throw(OSError()))
    assert secrets.protect("ключ") == "ключ"

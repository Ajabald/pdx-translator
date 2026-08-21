"""Storing the access keys.

What is checked is not the strength of the encryption — the system provides that
— but that the tool **does not lie about the state of a key**. A plain key shown
as protected is worse than a plain key shown honestly: in the second case the
human at least knows where it lies.
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
    """The keys written by a former version are read without loss."""
    assert secrets.unprotect("sk-старый-ключ") == "sk-старый-ключ"


def test_a_broken_blob_yields_nothing(monkeypatch) -> None:
    """A spoilt or foreign blob is no key.

    Returning rubbish would mean sending it to the service and getting an
    incomprehensible authorisation error instead of a plain «enter the key again».
    """
    assert secrets.unprotect("dpapi:не-base64-вовсе") == ""
    assert secrets.unprotect("dpapi:" + "AAAA") == ""


@pytest.mark.skipif(sys.platform == "win32", reason="проверяем поведение без DPAPI")
def test_without_dpapi_the_key_is_stored_plainly() -> None:
    assert secrets.protect("ключ") == "ключ"
    assert not secrets.is_protected("ключ")


def test_failure_falls_back_instead_of_losing_the_key(monkeypatch) -> None:
    """Losing the user's key is worse than keeping it unprotected."""
    monkeypatch.setattr(secrets, "available", lambda: True)
    monkeypatch.setattr(secrets, "_blob", lambda: (_ for _ in ()).throw(OSError()))
    assert secrets.protect("ключ") == "ключ"

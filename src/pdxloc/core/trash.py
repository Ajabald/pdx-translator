"""Deleting files into the recycle bin.

A project is months of a translator's work in a single file. A button that wipes
it beyond recovery is frightening enough that nobody uses it: opening Explorer is
easier. The recycle bin settles the question — misclick, take it back.

Windows does this through the shell (`SHFileOperationW` with the `FOF_ALLOWUNDO`
flag), so `ctypes` is enough and no dependency is pulled in for twenty lines.
Where the call is unavailable or fails we fall back to a plain delete, honestly —
but we say so to the caller, so it can warn.
"""
from __future__ import annotations

import sys
from pathlib import Path

# SHFileOperationW flags (shellapi.h)
_FO_DELETE = 3
_FOF_SILENT = 0x0004            # no progress window
_FOF_NOCONFIRMATION = 0x0010    # our own confirmation was already shown
_FOF_ALLOWUNDO = 0x0040         # to the bin, not to oblivion
_FOF_NOERRORUI = 0x0400         # we report the error ourselves, in our own words


def available() -> bool:
    """Whether the system recycle bin is there."""
    return sys.platform == "win32"


def _shell_delete(path: Path) -> bool:
    """Hand the file to the Windows shell. False means it did not work and the
    caller decides what to do."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # The list of paths ends with a DOUBLE null: one closes the string, the
    # other closes the list. Without the second the function reads past the end
    # of the buffer.
    op = SHFILEOPSTRUCTW(
        hwnd=None,
        wFunc=_FO_DELETE,
        pFrom=f"{path}\0\0",
        pTo=None,
        fFlags=_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI,
        fAnyOperationsAborted=False,
        hNameMappings=None,
        lpszProgressTitle=None,
    )
    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except (AttributeError, OSError):
        return False
    return result == 0 and not op.fAnyOperationsAborted


def remove(path: Path) -> str:
    """Delete a file. Returns «trash», «unlink» or «missing».

    Exceptions are not swallowed: the caller has to be able to tell the user that
    another program is holding the file, which is the commonest reason to fail.
    """
    path = Path(path)
    if not path.exists():
        return "missing"
    if available() and _shell_delete(path):
        return "trash"
    path.unlink()
    return "unlink"

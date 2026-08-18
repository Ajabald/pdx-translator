"""Удаление файлов в корзину.

Проект — это месяцы работы переводчика в одном файле. Кнопка, стирающая его
безвозвратно, страшна настолько, что ею не пользуются: проще открыть
проводник. Корзина снимает вопрос — ошибся, достал обратно.

Windows умеет это через оболочку (`SHFileOperationW` с флагом `FOF_ALLOWUNDO`),
поэтому обходимся `ctypes` и не тянем зависимость ради двадцати строк.
Там, где вызов недоступен или не удался, честно откатываемся на обычное
удаление — но сообщаем об этом вызывающему, чтобы тот мог предупредить.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Флаги SHFileOperationW (shellapi.h)
_FO_DELETE = 3
_FOF_SILENT = 0x0004            # без окна прогресса
_FOF_NOCONFIRMATION = 0x0010    # своё подтверждение уже показали
_FOF_ALLOWUNDO = 0x0040         # в корзину, а не насмерть
_FOF_NOERRORUI = 0x0400         # об ошибке скажем сами, своим текстом


def available() -> bool:
    """Есть ли системная корзина."""
    return sys.platform == "win32"


def _shell_delete(path: Path) -> bool:
    """Отдать файл оболочке Windows. False — не вышло, решать вызывающему."""
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

    # Список путей завершается ДВОЙНЫМ нулём: один — конец строки, второй —
    # конец списка. Без второго функция читает за границей буфера.
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
    """Удалить файл. Возвращает «trash», «unlink» или «missing».

    Исключение не глушим: вызывающий должен уметь сказать пользователю, что
    файл занят другой программой, — это самая частая причина отказа.
    """
    path = Path(path)
    if not path.exists():
        return "missing"
    if available() and _shell_delete(path):
        return "trash"
    path.unlink()
    return "unlink"

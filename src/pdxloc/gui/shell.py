"""Calls into Windows Explorer, all in one place.

There is exactly one non-obvious thing here, and the module exists for it:
`explorer /select,` must not be called with a list of arguments. Python joins a
list through `subprocess.list2cmdline`, which inserts a space after the comma,
so the command becomes `explorer /select, "D:\\path"` — Explorer cannot parse
that and silently opens the default folder instead of the file. That is exactly
why «Show original in Explorer» used to land on «Documents».
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def reveal(path: Path) -> None:
    """Show a file in Explorer with the file selected.

    If the file is gone, open its folder at least: saying nothing in answer to a
    button press is worse than showing not quite the right thing.
    """
    target = Path(path)
    if target.exists():
        native = os.path.normpath(str(target))
        subprocess.Popen(f'explorer /select,"{native}"')     # a string, not a list
    else:
        open_dir(target.parent)


def open_dir(path: Path) -> None:
    """Open a folder in Explorer, creating it if it is not there yet."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", os.path.normpath(str(target))])

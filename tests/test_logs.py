"""The diagnostic log: it writes, it survives a refusal and it does not drag Qt along."""
from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pdxloc import logs

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(autouse=True)
def clean_root(tmp_path, monkeypatch):
    """A directory of its own and a fresh root logger for every test."""
    from pdxloc import settings

    monkeypatch.setattr(settings, "app_root", lambda: tmp_path)
    monkeypatch.setattr(logs, "_configured", False)
    root = logging.getLogger()
    before = list(root.handlers)
    hook = sys.excepthook
    yield tmp_path
    for extra in [h for h in root.handlers if h not in before]:
        extra.close()
        root.removeHandler(extra)
    sys.excepthook = hook


def test_the_log_lands_next_to_the_application(clean_root) -> None:
    """Next to the application and not in %APPDATA%: the mode is portable."""
    path = logs.setup()
    assert path == clean_root / logs.LOG_NAME
    assert path.is_file()


def test_the_environment_is_written_first(clean_root) -> None:
    """The version, the Python and the system take half the questions off before the traceback."""
    from pdxloc import __version__

    path = logs.setup()
    text = path.read_text(encoding="utf-8")
    assert __version__ in text
    assert "Python" in text


def test_an_uncaught_exception_reaches_the_file(clean_root) -> None:
    """That is what the whole thing is for: at present such an exception goes nowhere."""
    path = logs.setup()
    try:
        raise ValueError("что-то пошло не так")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    text = path.read_text(encoding="utf-8")
    assert "что-то пошло не так" in text
    assert "ValueError" in text
    assert "Traceback" in text


def test_keyboard_interrupt_is_not_a_crash(clean_root) -> None:
    """Ctrl+C is no breakage, and there is no point littering the log with it."""
    path = logs.setup()
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())
    assert "KeyboardInterrupt" not in path.read_text(encoding="utf-8")


def test_a_read_only_folder_does_not_stop_the_application(monkeypatch) -> None:
    """An application that did not start because of the log is worse than one without a log.

    A directory happens to be read-only — a flash drive with protection, `Program
    Files` without rights — and that is no reason not to work.
    """
    def refuse(*_a, **_kw):
        raise OSError("только чтение")

    monkeypatch.setattr(logs.logging.handlers, "RotatingFileHandler", refuse)
    monkeypatch.setattr(logs, "_configured", False)
    assert logs.setup() is None


def test_setup_is_idempotent(clean_root) -> None:
    """A second call must not hang a second handler — the lines would be doubled."""
    logs.setup()
    count = len(logging.getLogger().handlers)
    logs.setup()
    assert len(logging.getLogger().handlers) == count


def test_logging_works_without_pyside(tmp_path) -> None:
    """`--scan-cli` lives without Qt, and the log is obliged to live there too.

    We check in a separate process: PySide6 is already loaded in this one, and
    substituting it in place would mean checking something other than what happens
    on a machine without Qt.
    """
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(SRC)!r})

        class Finder:
            def find_spec(self, name, path=None, target=None):
                if name == "PySide6" or name.startswith("PySide6."):
                    raise ImportError("PySide6 запрещён в этом тесте")
                return None
        sys.meta_path.insert(0, Finder())

        from pdxloc import logs, settings
        settings.app_root = lambda: __import__("pathlib").Path({str(tmp_path)!r})
        path = logs.setup()
        assert path is not None and path.is_file(), path
        assert "PySide6" not in sys.modules
        print("ok")
    """)
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout

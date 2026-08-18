"""Диагностический лог: пишет, переживает отказ и не тянет за собой Qt."""
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
    """Свой каталог и свежий корневой логгер на каждый тест."""
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
    """Рядом с приложением, а не в %APPDATA%: режим переносимый."""
    path = logs.setup()
    assert path == clean_root / logs.LOG_NAME
    assert path.is_file()


def test_the_environment_is_written_first(clean_root) -> None:
    """Версия, Python и система снимают половину вопросов до трассировки."""
    from pdxloc import __version__

    path = logs.setup()
    text = path.read_text(encoding="utf-8")
    assert __version__ in text
    assert "Python" in text


def test_an_uncaught_exception_reaches_the_file(clean_root) -> None:
    """Ради этого всё и делается: сейчас такое исключение уходит в никуда."""
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
    """Ctrl+C — не поломка, и засорять им лог незачем."""
    path = logs.setup()
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())
    assert "KeyboardInterrupt" not in path.read_text(encoding="utf-8")


def test_a_read_only_folder_does_not_stop_the_application(monkeypatch) -> None:
    """Приложение, не запустившееся из-за лога, хуже приложения без лога.

    Каталог бывает только на чтение — флешка с защитой, `Program Files` без
    прав, — и это не повод не работать.
    """
    def refuse(*_a, **_kw):
        raise OSError("только чтение")

    monkeypatch.setattr(logs.logging.handlers, "RotatingFileHandler", refuse)
    monkeypatch.setattr(logs, "_configured", False)
    assert logs.setup() is None


def test_setup_is_idempotent(clean_root) -> None:
    """Второй вызов не должен вешать второй обработчик — строки задвоились бы."""
    logs.setup()
    count = len(logging.getLogger().handlers)
    logs.setup()
    assert len(logging.getLogger().handlers) == count


def test_logging_works_without_pyside(tmp_path) -> None:
    """`--scan-cli` живёт без Qt, и лог обязан жить там же.

    Проверяем в отдельном процессе: PySide6 уже загружен в этом, и подменить
    его на месте — значит проверить не то, что происходит на машине без Qt.
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

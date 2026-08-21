"""Translating the application strings — the one point they all go through.

The strings in the code are written in English: `pyside6-lupdate` keys a
translation to the text of the original, so the original has to be the language
everyone else will translate from. Russian is therefore as much a translation as
Chinese and lives in `gui/translations/pdxloc_ru.ts`.

**The core must not depend on Qt.** `--scan-cli` works without PySide6, and the
quality checks run in tests with no window. So the module degrades to the
identity function when Qt is absent, by the same trick as `settings._get`.

There are two ways to mark a string, and they must not be confused:

* `QT_TRANSLATE_NOOP("Context", "Text")` — **for module-level tables**
  (`actions.ACTIONS`, `qa_rules.BUILTIN_RULES`, `statuses.STATUS_LABELS`). Those
  are evaluated at import time, when no translator is installed yet: translating
  there means remembering the untranslated form forever. It returns the string as
  it is, and the translation happens at display time;
* `translate("Context", "Text")` — **at display time**.

The name `translate` is not an accident: lupdate recognises the call by its name.
A function called `tr` would be parsed as a QObject method with the signature
(text, disambiguation) — and the second argument would end up as a comment
instead of a context. `QT_TRANSLATE_NOOP` is re-exported under its own name for
the same reason: `from ... import QT_TRANSLATE_NOOP as NOOP` makes the string
invisible to the collector.
"""
from __future__ import annotations

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtCore import QT_TRANSLATE_NOOP        # noqa: F401 — re-export
except ImportError:                                     # no Qt: --scan-cli, core tests
    QCoreApplication = None

    def QT_TRANSLATE_NOOP(context: str, text: str) -> str:      # noqa: N802
        return text


def translate(context: str, text: str, disambiguation: str | None = None,
              n: int = -1) -> str:
    """Translate a string at display time.

    Without Qt — and before a translator is installed — it returns the original,
    which is the English interface itself rather than a stand-in.

    The call must take no further arguments: lupdate parses it by shape and on an
    unfamiliar argument, a keyword one included, **loses the string in silence**.
    That is why substituting values lives in `fill`.
    """
    if QCoreApplication is None:
        return text
    return QCoreApplication.translate(context, text, disambiguation, n)


def fill(template: str, *values) -> str:
    """Substitute values into `%1`, `%2`… of an already translated template.

    A separate function rather than an argument to `translate`, for the prosaic
    reason above. The `%N` form is a Qt convention: Linguist shows such
    substitutions to the translator separately and complains when one goes
    missing. Joining a string out of pieces is not allowed at all: word order
    differs between languages, and the translator would receive fragments with no
    way to reorder them.
    """
    text = template
    for index, value in enumerate(values, start=1):
        text = text.replace(f"%{index}", str(value))
    return text

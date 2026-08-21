"""The mechanics of translation: the core without Qt, the files, the live switch.

The main property watched over here: **the core works without PySide6**. The
`--scan-cli` mode and the quality checks are driven without a window, and should
`core/i18n` drag Qt along with it, the whole core would fall over at once — and
that would not be noticed at once.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc.core import i18n  # noqa: E402
from pdxloc.core import statuses as statuses_mod  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.gui import language  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"
TRANSLATIONS = SRC / "pdxloc" / "gui" / "translations"
TOOLS = Path(__file__).resolve().parents[1] / "tools"

# language -> (the module with the pairs, the name of the dictionary); as in tools/seed_ts.py
PAIR_SOURCES = {"ru": ("ru_translations", "RU"), "zh_CN": ("zh_translations", "ZH")}


def pairs(code: str) -> dict[str, dict[str, str]]:
    """The dictionary «context → {original: translation}» out of tools/."""
    import importlib.util

    module_name, table = PAIR_SOURCES[code]
    spec = importlib.util.spec_from_file_location(
        module_name, TOOLS / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, table)


def ts_sources(code: str) -> set[tuple[str, str]]:
    import xml.etree.ElementTree as ET

    tree = ET.parse(TRANSLATIONS / f"{language.PREFIX}{code}.ts")
    return {(context.findtext("name") or "", message.findtext("source") or "")
            for context in tree.getroot().findall("context")
            for message in context.findall("message")}


# --- the core without Qt ------------------------------------------------


def test_core_i18n_works_without_pyside(tmp_path) -> None:
    """Importing the core with PySide6 unavailable must not fall over.

    We check in a separate process: PySide6 is already loaded in this one, and
    substituting it in place would mean checking something other than what
    happens on a machine without Qt.
    """
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(SRC)!r})

        # запрещаем импорт PySide6 целиком
        class Blocker:
            def find_module(self, name, path=None):
                if name == "PySide6" or name.startswith("PySide6."):
                    raise ImportError("PySide6 запрещён в этом тесте")
                return None
        class Finder:
            def find_spec(self, name, path=None, target=None):
                if name == "PySide6" or name.startswith("PySide6."):
                    raise ImportError("PySide6 запрещён в этом тесте")
                return None
        sys.meta_path.insert(0, Finder())

        from pdxloc.core import i18n, statuses, qa_rules, markup
        # машинный перевод тоже ядро: провайдеры ходят в сеть стандартной
        # библиотекой и настроек не читают — иначе потянули бы за собой Qt
        from pdxloc.core import mt, mt_errors, mt_run, mt_providers
        assert i18n.translate("Ctx", "Text") == "Text"
        assert i18n.QT_TRANSLATE_NOOP("Ctx", "Text") == "Text"
        assert statuses.label(statuses.Status.TRANSLATED)
        assert len(qa_rules.BUILTIN_RULES) > 5
        assert mt.shield_tags("[GetName] x")[1]
        assert mt_run.plan_batches(["a"], 10)[0] == [[0]]
        assert mt_errors.MtQuotaError("x").retry_after is None
        assert "none" in mt_providers.PROVIDERS
        assert "PySide6" not in sys.modules
        print("ok")
    """)
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_noop_returns_the_source_text() -> None:
    """A mark is not a translation: it is obliged to return the string untouched."""
    assert i18n.QT_TRANSLATE_NOOP("Ctx", "Scan") == "Scan"


def test_status_labels_go_through_the_translating_helper() -> None:
    """Going to the dictionary directly will not do — it is not translated."""
    for status in Status:
        assert statuses_mod.label(status)
    assert statuses_mod.label("такого статуса нет") == "такого статуса нет"


# --- the translation files ----------------------------------------------


def test_every_declared_language_is_either_source_or_has_a_file() -> None:
    """A menu item without a .qm is a promise the application will not keep."""
    for code in language.LANGUAGES:
        if code == language.SOURCE:
            continue
        ts = TRANSLATIONS / f"{language.PREFIX}{code}.ts"
        assert ts.is_file(), f"нет файла перевода для {code}: {ts}"


def test_available_lists_only_compiled_languages() -> None:
    have = language.available()
    assert language.SOURCE in have
    for code in have:
        if code == language.SOURCE:
            continue
        assert (TRANSLATIONS / f"{language.PREFIX}{code}.qm").is_file()


@pytest.mark.parametrize(
    "ts", sorted(TRANSLATIONS.glob("pdxloc_*.ts")) or [None],
    ids=lambda p: p.name if p else "нет-файлов")
def test_compiled_translation_is_not_older_than_its_source(ts) -> None:
    """The `.qm` is built out of the `.ts`: forgetting to rebuild means showing the old text."""
    if ts is None:
        pytest.skip("файлы переводов ещё не заведены")
    qm = ts.with_suffix(".qm")
    assert qm.is_file(), f"не собран {qm.name}: tools/i18n.py release"
    assert qm.stat().st_mtime >= ts.stat().st_mtime - 1, (
        f"{qm.name} старее {ts.name} — пересоберите: tools/i18n.py release")


@pytest.mark.parametrize("code", sorted(PAIR_SOURCES))
def test_no_pair_is_left_without_an_original(code) -> None:
    """A translation for which no original was found in the `.ts` is a lost translation.

    That is exactly how it happens: the English string is edited in the code and
    the pair in `tools/` is forgotten. There is not a single error at that — the
    translation simply stops being substituted, and that shows only in a foreign
    language.
    """
    known = ts_sources(code)
    orphans = [(context, source)
               for context, table in pairs(code).items() for source in table
               if (context, source) not in known]
    assert not orphans, (
        f"переводов без оригинала: {len(orphans)}; "
        f"первый — {orphans[0]}; строку правили в коде, а в tools/ нет")


@pytest.mark.parametrize("code", sorted(PAIR_SOURCES))
def test_every_original_has_a_pair(code) -> None:
    """An untranslated string silently stays English in the middle of another language."""
    table = pairs(code)
    missing = [(context, source) for context, source in ts_sources(code)
               if source not in table.get(context, {})]
    assert not missing, (
        f"без перевода: {len(missing)}; первая — {missing[0]}")


def test_the_checked_mark_counts_the_rows_it_was_given() -> None:
    """The proofreading mark is obliged to diverge once strings have been added.

    Otherwise it would silently spread onto a string a human has not seen — and
    the point of the mark is exactly to tell the checked from the machine-made. A
    divergence returns `unfinished` to the whole context: better to ask once too
    often.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "zh_translations", TOOLS / "zh_translations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stale = {context: count for context, count in module.CHECKED.items()
             if count != len(module.ZH.get(context, {}))}
    assert not stale, (
        f"пометка о вычитке разошлась с числом строк: {stale}; "
        f"перечитайте контекст и поправьте число в CHECKED")
    unknown = set(module.CHECKED) - set(module.ZH)
    assert not unknown, f"вычитан контекст, которого нет: {unknown}"


# --- choosing the language ----------------------------------------------


def test_system_language_is_picked_when_nothing_is_saved(monkeypatch) -> None:
    monkeypatch.setattr(language, "available",
                        lambda: {"en": "English", "ru": "Русский"})
    monkeypatch.setattr("PySide6.QtCore.QLocale.system",
                        staticmethod(lambda: __import__(
                            "PySide6.QtCore", fromlist=["QLocale"]).QLocale("ru_RU")))
    assert language.system_default() == "ru"


def test_unknown_language_falls_back_to_the_source(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    language.apply(QApplication.instance(), "эльфийский", save=False)
    assert language.current() == language.SOURCE


def test_switching_to_the_same_language_is_not_an_event(qtbot) -> None:
    """A redraw is expensive, and there must be none of it for nothing."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    language.apply(app, language.SOURCE, save=False)
    fired = []
    language.notifier.changed.connect(lambda: fired.append(1))
    try:
        language.apply(app, language.SOURCE, save=False)
        assert fired == []
    finally:
        language.notifier.changed.disconnect()


# --- the strings in the code --------------------------------------------


def test_translation_context_is_always_a_literal() -> None:
    """A variable context lupdate does not allow — and it loses the string silently.

    This is exactly what burned us: `CTX = "Actions"` next to it and
    `translate(CTX, …)` in the code look impeccable, while the builder found 1
    string out of 55. The error shows in no way at all — there simply will be no
    translation, and it is the translator who notices it, not the developer.
    """
    import ast

    bad = []
    for path in sorted((SRC / "pdxloc").rglob("*.py")):
        if path.name == "i18n.py":
            continue        # there lies the implementation itself: the context comes as an argument
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in ("translate", "QT_TRANSLATE_NOOP"):
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                bad.append(f"{path.name}:{node.lineno}")
    assert not bad, ("контекст перевода обязан быть строковым литералом:\n"
                     + "\n".join(bad))


def test_translation_calls_are_never_nested_in_an_fstring() -> None:
    """`f"{translate(…)}"` lupdate does not parse, and it loses the string.

    The third silent loss of the same kind: the code works, the translation simply
    does not appear. It has to be computed in a variable of its own before the
    substitution.
    """
    import ast

    bad = []
    for path in sorted((SRC / "pdxloc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                name = (getattr(inner.func, "id", None)
                        or getattr(inner.func, "attr", None))
                if name in ("translate", "QT_TRANSLATE_NOOP"):
                    bad.append(f"{path.name}:{inner.lineno}")
    assert not bad, ("перевод внутри f-строки сборщик не увидит — вынесите "
                     "вызов в переменную:\n" + "\n".join(bad))


def test_marked_strings_actually_reach_the_translation_file() -> None:
    """The assembled .ts must not be emptier than the marking in the code.

    A crude but effective reconciliation: should the next table get marked past
    the builder, the number in the .ts will stop growing, and the test will show it.
    """
    import xml.etree.ElementTree as ET

    ts = TRANSLATIONS / f"{language.PREFIX}ru.ts"
    if not ts.is_file():
        pytest.skip("файл перевода ещё не собран")
    root = ET.parse(ts).getroot()
    found = sum(len(ctx.findall("message")) for ctx in root.findall("context"))
    assert found >= 30, (
        f"в переводе всего {found} строк — похоже, разметка не дошла до "
        f"lupdate; пересоберите: tools/i18n.py update")


def test_no_module_defines_a_function_named_tr() -> None:
    """`tr(a, b)` lupdate reads as (text, disambiguation), not as (context, text).

    Such a function would silently take the context off into a comment, and the
    translations would come apart over a nameless context. A check by grep is
    cheaper than reading a .ts by eye.
    """
    bad = []
    for path in sorted((SRC / "pdxloc").rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*def tr\s*\(", line):
                bad.append(f"{path.name}:{n}")
    assert not bad, ("функция с именем tr сбивает lupdate — назовите translate:\n"
                     + "\n".join(bad))

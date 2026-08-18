"""Механика перевода: ядро без Qt, файлы переводов, живая смена языка.

Главное свойство, которое здесь стережётся: **ядро работает без PySide6**.
Режим `--scan-cli` и проверки качества гоняются без окна, и стоит `core/i18n`
потянуть за собой Qt — упадёт всё ядро разом, а заметят это не сразу.
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

# язык -> (модуль с парами, имя словаря); то же, что в tools/seed_ts.py
PAIR_SOURCES = {"ru": ("ru_translations", "RU"), "zh_CN": ("zh_translations", "ZH")}


def pairs(code: str) -> dict[str, dict[str, str]]:
    """Словарь «контекст → {оригинал: перевод}» из tools/."""
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


# --- ядро без Qt --------------------------------------------------------


def test_core_i18n_works_without_pyside(tmp_path) -> None:
    """Импорт ядра при недоступном PySide6 не должен падать.

    Проверяем в отдельном процессе: PySide6 уже загружен в этом, и подменить
    его на месте — значит проверить не то, что происходит на машине без Qt.
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
    """Пометка — не перевод: она обязана вернуть строку нетронутой."""
    assert i18n.QT_TRANSLATE_NOOP("Ctx", "Scan") == "Scan"


def test_status_labels_go_through_the_translating_helper() -> None:
    """Обращаться к словарю напрямую нельзя — он не переведён."""
    for status in Status:
        assert statuses_mod.label(status)
    assert statuses_mod.label("такого статуса нет") == "такого статуса нет"


# --- файлы переводов ----------------------------------------------------


def test_every_declared_language_is_either_source_or_has_a_file() -> None:
    """Пункт меню без .qm — обещание, которого приложение не выполнит."""
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
    """`.qm` собран из `.ts`: забыть пересобрать — значит показать старый текст."""
    if ts is None:
        pytest.skip("файлы переводов ещё не заведены")
    qm = ts.with_suffix(".qm")
    assert qm.is_file(), f"не собран {qm.name}: tools/i18n.py release"
    assert qm.stat().st_mtime >= ts.stat().st_mtime - 1, (
        f"{qm.name} старее {ts.name} — пересоберите: tools/i18n.py release")


@pytest.mark.parametrize("code", sorted(PAIR_SOURCES))
def test_no_pair_is_left_without_an_original(code) -> None:
    """Перевод, которому в `.ts` не нашлось оригинала, — потерянный перевод.

    Так это и происходит: английскую строку правят в коде, а пару в `tools/`
    забывают. Ошибки при этом нет ни одной — перевод просто перестаёт
    подставляться, и заметно это лишь на чужом языке.
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
    """Непереведённая строка молча остаётся английской посреди чужого языка."""
    table = pairs(code)
    missing = [(context, source) for context, source in ts_sources(code)
               if source not in table.get(context, {})]
    assert not missing, (
        f"без перевода: {len(missing)}; первая — {missing[0]}")


def test_the_checked_mark_counts_the_rows_it_was_given() -> None:
    """Пометка о вычитке обязана расходиться, когда строк прибавилось.

    Иначе она молча распространилась бы на строку, которой человек не видел, —
    а смысл пометки ровно в том, чтобы отличать проверенное от собранного
    машиной. Расхождение возвращает контексту `unfinished` целиком: лучше
    спросить лишний раз.
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


# --- выбор языка --------------------------------------------------------


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
    """Перерисовка стоит дорого, и на пустом месте её быть не должно."""
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


# --- строки в коде ------------------------------------------------------


def test_translation_context_is_always_a_literal() -> None:
    """Контекст переменной lupdate не разрешает — и молча теряет строку.

    Ровно на этом обжигались: `CTX = "Actions"` рядом и `translate(CTX, …)` в
    коде выглядят безупречно, а сборщик нашёл 1 строку из 55. Ошибка не
    проявляется никак — просто перевода не будет, и заметит это переводчик,
    а не разработчик.
    """
    import ast

    bad = []
    for path in sorted((SRC / "pdxloc").rglob("*.py")):
        if path.name == "i18n.py":
            continue        # там сама реализация: контекст приходит аргументом
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
    """`f"{translate(…)}"` lupdate не разбирает и строку теряет.

    Третья по счёту тихая потеря того же рода: код работает, перевод просто
    не появляется. Вычислять надо в отдельной переменной перед подстановкой.
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
    """Собранный .ts не должен быть пустее, чем разметка в коде.

    Грубая, но действенная сверка: если очередная таблица разметится мимо
    сборщика, число в .ts перестанет расти, и тест это покажет.
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
    """`tr(a, b)` lupdate читает как (текст, уточнение), а не (контекст, текст).

    Такая функция молча увела бы контекст в комментарий, и переводы разъехались
    бы по безымянному контексту. Проверка грепом дешевле, чем разбор .ts глазами.
    """
    bad = []
    for path in sorted((SRC / "pdxloc").rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*def tr\s*\(", line):
                bad.append(f"{path.name}:{n}")
    assert not bad, ("функция с именем tr сбивает lupdate — назовите translate:\n"
                     + "\n".join(bad))

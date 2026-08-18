"""Обмен настройкой проверок: файл `.pdxqa`.

Зачем файл, когда настройка и так лежит в двух местах. Оба места — не то:
глобальный слой привязан к машине, проектный уезжает только вместе с проектом.
А делятся именно настройкой: команда договаривается, что считать ошибкой, один
человек это настраивает, остальные принимают. Тот же приём у Xbench (`.xbckl`) и
у Okapi CheckMate.

**Файл самодостаточен.** Внутри — пресет по имени, дельта относительно
встроенных значений и свои правила целиком. Не относительно слоя, лежащего ниже
у автора: у принимающего этого слоя нет, и набор собрался бы другой. Это
единственное место, где дельта считается не от соседнего слоя.

Читаем оборонительно. Чужой файл — данные, а не команда: незнакомые правила,
параметры, виды и серьёзности пропускаются, о числе пропущенного сообщается
человеку. Молчаливый пропуск здесь недопустим ровно потому, что он допустим
внутри оверлея: там дело в разнице версий, а тут пользователь ждёт, что приехало
всё, и должен узнать, если это не так.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from collections.abc import Mapping

from pdxloc.core import qa_rules
from pdxloc.core.qa_rules import RuleSet

FORMAT = "pdxqa"
VERSION = 1
SUFFIX = ".pdxqa"


class ExchangeError(Exception):
    """Файл не прочитать — показывается пользователю как есть."""


@dataclass(frozen=True, slots=True)
class Bundle:
    """Что приехало из файла.

    Набор из файла **заменяет** настройку слоя целиком, а не смешивается с ней.
    Умное слияние («возьмём только то, чего файл касался») выглядит вежливее, но
    предсказать его результат нельзя: пресет из файла меняет основание всем
    правилам сразу, и половина набора оказалась бы от одного источника, половина
    от другого. Что именно приедет, показывается до применения.
    """

    preset: str
    overlay: dict
    changed: tuple[str, ...] = ()       # встроенные правила с правками
    added: tuple[str, ...] = ()         # свои правила
    skipped: tuple[str, ...] = ()       # что не понято

    def ruleset(self, locale: str = "") -> RuleSet:
        """Набор из файла. Язык перевода — тот же, что у остальных слоёв."""
        return qa_rules.resolve(self.overlay, locale=locale)


def dump(preset: str, rules: RuleSet, *, app_version: str = "",
         locale: str = "") -> dict:
    """Содержимое файла для набора `rules` с пресетом `preset`.

    `locale` — язык перевода, на котором набор собирали. Он нужен ровно затем,
    чтобы не уехать в файл: языковые правила гасятся основанием, и без него
    француз записал бы принимающему «выключить правила русской грамматики»
    просто потому, что у него самого они молчали.
    """
    overlay = qa_rules.make_overlay(preset, rules, locale=locale)
    return {
        "format": FORMAT,
        "version": VERSION,
        "app": app_version,
        "exported": date.today().isoformat(),
        "preset": overlay.get("preset"),
        "rules": overlay.get("rules", {}),
        "custom": overlay.get("custom", []),
    }


def write(path: Path, preset: str, rules: RuleSet, *,
          app_version: str = "", locale: str = "") -> Path:
    path = Path(path)
    if path.suffix.lower() != SUFFIX:
        path = path.with_suffix(SUFFIX)
    path.write_text(
        json.dumps(dump(preset, rules, app_version=app_version, locale=locale),
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    return path


def parse(data: Mapping) -> Bundle:
    """Разобрать содержимое файла. Незнакомое — в `skipped`."""
    if not isinstance(data, Mapping) or data.get("format") != FORMAT:
        raise ExchangeError("not a pdxqa file")
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError) as e:
        # Номер версии — тоже чужие данные: `int("вчера")` вылетал бы мимо
        # ExchangeError, и окно показало бы не сообщение, а падение.
        raise ExchangeError(f"unreadable version: {data.get('version')!r}") from e
    if version > VERSION:
        raise ExchangeError("made by a newer version")

    skipped: list[str] = []
    preset = data.get("preset")
    if preset not in qa_rules.PRESETS:
        if preset:
            skipped.append(str(preset))
        preset = qa_rules.CUSTOM

    raw_rules = data.get("rules")
    deltas: dict[str, dict] = {}
    if isinstance(raw_rules, Mapping):
        for rule_id, delta in raw_rules.items():
            if rule_id in qa_rules.BY_ID and isinstance(delta, Mapping):
                deltas[str(rule_id)] = dict(delta)
            else:
                skipped.append(str(rule_id))

    raw_custom = data.get("custom")
    custom: list[dict] = []
    if isinstance(raw_custom, (list, tuple)):
        for record in raw_custom:
            rule = qa_rules.load_user_rule(record) if isinstance(record, Mapping) else None
            if rule is None:
                name = record.get("id") if isinstance(record, Mapping) else record
                skipped.append(str(name))
            else:
                custom.append(qa_rules.dump_user_rule(rule))

    overlay = {"version": qa_rules.OVERLAY_VERSION,
               "preset": None if preset == qa_rules.CUSTOM else preset,
               "rules": deltas}
    if custom:
        overlay["custom"] = custom
    return Bundle(
        preset=preset,
        overlay=overlay,
        changed=tuple(deltas),
        added=tuple(r["id"] for r in custom),
        skipped=tuple(skipped),
    )


def read(path: Path) -> Bundle:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise ExchangeError(str(e)) from e
    except ValueError as e:
        raise ExchangeError(f"broken JSON: {e}") from e
    return parse(data)



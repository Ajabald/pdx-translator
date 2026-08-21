"""Sharing the check settings: the `.pdxqa` file.

Why a file, when the settings already live in two places. Because neither place
will do: the global layer is tied to the machine, the project one travels only
with the project. And it is the settings people share — a team agrees on what
counts as an error, one person configures it, the rest take it. Xbench does the
same with `.xbckl`, and so does Okapi CheckMate.

**The file stands alone.** Inside it are the preset by name, the delta against
the built-in values, and the custom rules in full. Not the delta against the
layer below on the author's machine: the recipient has no such layer, and the set
would come out different. This is the one place where a delta is computed against
something other than the neighbouring layer.

Reading is defensive. Somebody else's file is data, not a command: unknown rules,
parameters, kinds and severities are skipped, and the number skipped is reported
to the person. A silent skip is unacceptable here for exactly the reason it is
acceptable inside an overlay: there it is a difference of versions, while here
the user expects everything to have arrived and must be told when it did not.
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
    """The file cannot be read; the message is shown to the user as it is."""


@dataclass(frozen=True, slots=True)
class Bundle:
    """What arrived from the file.

    The set from a file **replaces** the layer's settings whole rather than
    mixing with them. A clever merge — «take only what the file touched» — looks
    politer, but its result cannot be predicted: the preset in the file changes
    the base of every rule at once, and half the set would come from one source
    and half from the other. What exactly will arrive is shown before it is
    applied.
    """

    preset: str
    overlay: dict
    changed: tuple[str, ...] = ()       # built-in rules that were edited
    added: tuple[str, ...] = ()         # the user's own rules
    skipped: tuple[str, ...] = ()       # what was not understood

    def ruleset(self, locale: str = "") -> RuleSet:
        """The set from the file. The translation language is the one the other layers
        use."""
        return qa_rules.resolve(self.overlay, locale=locale)


def dump(preset: str, rules: RuleSet, *, app_version: str = "",
         locale: str = "") -> dict:
    """The contents of a file for the set `rules` under the preset `preset`.

    `locale` is the translation language the set was assembled under. It is there
    precisely so that it does not travel into the file: language rules are
    silenced by the base, and without it a French user would write «switch the
    Russian grammar rules off» into the recipient's settings simply because they
    were silent on their own machine.
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
    # Файл мог быть выгружен до 0.1.2, когда игра и язык жили в одном наборе.
    preset = qa_rules.PRESET_ALIASES.get(preset, preset)
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



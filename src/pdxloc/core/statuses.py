"""Statuses of translatable rows: the database values and the labels shown.

The colours live in gui/theme.py — there are two sets of them, light and dark,
and the core, which runs without an interface at all, has no use for either.

The labels are marked with `QT_TRANSLATE_NOOP` rather than translated in place:
the table is built at import time, when no translator is installed yet. `label()`
translates them at the moment of display — go through it, not through the dict.
"""
from __future__ import annotations

from enum import StrEnum

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

CTX = "Statuses"


class Status(StrEnum):
    UNTRANSLATED = "untranslated"
    MACHINE = "machine"          # machine translation, unseen by a human
    AUTO = "auto"                # filled from memory, needs review
    TRANSLATED = "translated"
    REVIEWED = "reviewed"
    STALE = "stale"              # the source changed after the translation
    IGNORED = "ignored"          # nothing to translate (a row of bare tags, say)
    CUSTOM = "custom"            # the user's own mark (status 150 in EET)


STATUS_LABELS: dict[Status, str] = {
    Status.UNTRANSLATED: QT_TRANSLATE_NOOP("Statuses", "Not translated"),
    # «unchecked» has to stay in the label: «Machine» on its own reads as a
    # finished state, which is exactly what machine translation is not
    Status.MACHINE: QT_TRANSLATE_NOOP("Statuses", "Machine (unchecked)"),
    Status.AUTO: QT_TRANSLATE_NOOP("Statuses", "Auto (from memory)"),
    Status.TRANSLATED: QT_TRANSLATE_NOOP("Statuses", "Translated"),
    Status.REVIEWED: QT_TRANSLATE_NOOP("Statuses", "Reviewed"),
    Status.STALE: QT_TRANSLATE_NOOP("Statuses", "Outdated"),
    Status.IGNORED: QT_TRANSLATE_NOOP("Statuses", "Ignored"),
    Status.CUSTOM: QT_TRANSLATE_NOOP("Statuses", "Custom"),
}


def label(status: Status | str) -> str:
    """The status label in the current interface language."""
    try:
        key = Status(status)
    except ValueError:
        return str(status)
    return translate("Statuses", STATUS_LABELS[key])

# The translator's working order, not the alphabet of the values: the status-bar
# chips, the filter entries and the sorting of the «Status» column all follow it.
# One list for the whole application — otherwise the three drift apart the moment
# a status is added.
#
# «Machine» stands before «Auto» on purpose: a fill from memory is an exact match
# with a translation somebody once made by hand, while machine translation was
# never seen by a human at all. The order is a working one, and the least
# trustworthy comes first.
STATUS_ORDER: tuple[Status, ...] = (
    Status.UNTRANSLATED, Status.MACHINE, Status.AUTO, Status.TRANSLATED,
    Status.REVIEWED, Status.STALE, Status.CUSTOM, Status.IGNORED,
)

STATUS_RANK: dict[str, int] = {s.value: i for i, s in enumerate(STATUS_ORDER)}

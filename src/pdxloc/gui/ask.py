"""Reminders that always have a way out.

The trick is taken from ESP/ESM Translator. Every forced modal there has a
matching «always do this, without asking» setting
(`Options.Toujours ouvrir cette langue`, `Options.Toujours traduire dans cette
langue`, `Message.ToujoursOuvrirCetteLangue`). Without such a way out a modal
shown for the third time stops being read: people dismiss it unseen, and the
first genuinely important warning leaves with it.

So the application has no reminders «just because»: each one is either asked once
in the lifetime of the install (the first-run wizard) or goes through `ask_once`
and can be silenced for good.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QMessageBox

from pdxloc.core.i18n import translate
from pdxloc.gui import prefs

PREFIX = "ask/"


def _key(name: str) -> str:
    return f"{PREFIX}{name}"


def muted(name: str) -> bool:
    """Whether the user asked not to be bothered about this again."""
    return bool(prefs.get_flag(_key(name)))


def unmute(name: str) -> None:
    """Bring a reminder back. «Preferences» needs it: silenced quietly is forever."""
    prefs.set_flag(_key(name), False)


def unmute_all() -> None:
    for name in KNOWN:
        unmute(name)


def any_muted() -> bool:
    """Whether there is anything to bring back, so «Preferences» can hide a dead
    checkbox."""
    return any(muted(name) for name in KNOWN)


def ask_once(parent, name: str, title: str, text: str,
             *, buttons=QMessageBox.Yes | QMessageBox.No) -> int:
    """Ask, unless asked not to. Returns the button that was pressed.

    A silenced question answers `No` — «do nothing». The default is deliberately
    the cautious one: the «do not ask again» box is ticked to be left alone by an
    offer, not to have it carried out unattended.
    """
    if muted(name):
        return QMessageBox.No

    box = QMessageBox(QMessageBox.Question, title, text, buttons, parent)
    again = QCheckBox(translate("Ask", "Do not ask again"))
    box.setCheckBox(again)
    answer = box.exec()
    if again.isChecked():
        prefs.set_flag(_key(name), True)
    return answer


# The names of the reminders. «Preferences» needs the list: without it there
# would be nothing to bring a silenced reminder back with, and a setting that
# cannot be undone is a trap.
NO_TM_DATABASES = "no_tm_databases"

KNOWN: tuple[str, ...] = (NO_TM_DATABASES,)

"""Напоминания, у которых есть постоянный выход.

Приём снят с ESP/ESM Translator. У него на каждую принудительную модалку есть
парная настройка «всегда так делать, без подтверждения»
(`Options.Toujours ouvrir cette langue`, `Options.Toujours traduire dans cette
langue`, `Message.ToujoursOuvrirCetteLangue`). Без такого выхода модалка,
показанная в третий раз, перестаёт читаться: её закрывают не глядя, и первое же
важное предупреждение уезжает вместе с ней.

Поэтому в приложении нет напоминаний «просто так»: каждое либо задаётся один
раз за жизнь (мастер первого запуска), либо проходит через `ask_once` и умеет
замолчать навсегда.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QMessageBox

from pdxloc.core.i18n import translate
from pdxloc.gui import prefs

PREFIX = "ask/"


def _key(name: str) -> str:
    return f"{PREFIX}{name}"


def muted(name: str) -> bool:
    """Просил ли пользователь больше не спрашивать об этом."""
    return bool(prefs.get_flag(_key(name)))


def unmute(name: str) -> None:
    """Вернуть напоминание. Нужно «Параметрам»: заглушённое молча — навсегда."""
    prefs.set_flag(_key(name), False)


def unmute_all() -> None:
    for name in KNOWN:
        unmute(name)


def any_muted() -> bool:
    """Есть ли что возвращать. «Параметрам» — чтобы не показывать мёртвую галку."""
    return any(muted(name) for name in KNOWN)


def ask_once(parent, name: str, title: str, text: str,
             *, buttons=QMessageBox.Yes | QMessageBox.No) -> int:
    """Спросить, если не просили молчать. Возвращает нажатую кнопку.

    Заглушённый вопрос отвечает `No` — «ничего не делаем». Умолчание выбрано
    осторожным намеренно: галка «больше не спрашивать» ставится, чтобы от
    предложения отвязались, а не чтобы оно исполнялось само.
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


# Имена напоминаний. Список нужен «Параметрам»: без него вернуть заглушённое
# было бы нечем, а настройка, которую невозможно отменить, — ловушка.
NO_TM_DATABASES = "no_tm_databases"

KNOWN: tuple[str, ...] = (NO_TM_DATABASES,)

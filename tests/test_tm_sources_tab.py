"""Вкладка «Базы»: включение и отключение баз памяти.

Модуль не был покрыт вовсе, а через него проходит единственная в приложении
дорога к тому, какие базы участвуют в подсказках. Ошибка тут не падает, а тихо
меняет результат подсказок — то есть замечают её не сразу и не там.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from pdxloc import project as project_mod  # noqa: E402
from pdxloc import settings  # noqa: E402
from pdxloc.core import games, tm_import  # noqa: E402
from pdxloc.gui.tm_sources_tab import TmSourcesTab  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'


@pytest.fixture
def bdd(tmp_path, monkeypatch, make_tree):
    """Папка баз с одной собранной базой, подходящей проекту."""
    root = tmp_path / "Bdd"
    monkeypatch.setattr(settings, "bdd_dir", lambda: root)
    (root / games.CK3.upper()).mkdir(parents=True, exist_ok=True)

    en = make_tree({"m_l_english.yml": EN}, "src")
    ru = make_tree({"m_l_russian.yml": RU}, "tgt")
    out = root / games.CK3.upper() / "Ваниль_english-russian.pdxtm"
    tm_import.build_tm_from_dirs(
        en, ru, out, name="Ваниль", src_lang="english", tgt_lang="russian",
        kind="game", game=games.CK3)
    return root, out


@pytest.fixture
def tab(bdd, tmp_path, qtbot, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "pen")
    ru = make_tree({}, "pru")
    conn = project_mod.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en, tgt_root=ru)
    widget = TmSourcesTab(conn)
    qtbot.addWidget(widget)
    yield widget, conn
    widget.shutdown()
    conn.close()


def item_names(widget):
    return [widget.list.item(i).data(Qt.UserRole)
            for i in range(widget.list.count())]


# --- список ----------------------------------------------------------------


def test_a_built_database_shows_up(tab, bdd) -> None:
    widget, _conn = tab
    _root, out = bdd
    assert out.name in item_names(widget)


def test_nothing_is_attached_until_asked(tab) -> None:
    """Собранная база не подключается сама — это выбор переводчика."""
    widget, conn = tab
    assert project_mod.get_tm_sources(conn) == []
    assert widget.list.item(0).checkState() == Qt.Unchecked


# --- включение и отключение ------------------------------------------------


def test_ticking_attaches_the_database(tab) -> None:
    widget, conn = tab
    widget.list.item(0).setCheckState(Qt.Checked)

    assert project_mod.get_tm_sources(conn) == [widget.list.item(0).data(Qt.UserRole)]
    # представление пересобрано: база участвует в поиске прямо сейчас
    assert conn.execute("SELECT COUNT(*) FROM tm_all").fetchone()[0] > 0


def test_unticking_detaches_it_again(tab) -> None:
    widget, conn = tab
    widget.list.item(0).setCheckState(Qt.Checked)
    assert conn.execute("SELECT COUNT(*) FROM tm_all").fetchone()[0] > 0

    widget.list.item(0).setCheckState(Qt.Unchecked)
    assert project_mod.get_tm_sources(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM tm_all").fetchone()[0] == 0


def test_a_change_is_announced_outwards(tab, qtbot) -> None:
    """Сигнал наружу — то, чем шапка окна и подсказки узнают о смене набора."""
    widget, _conn = tab
    with qtbot.waitSignal(widget.sourcesChanged, timeout=1000):
        widget.list.item(0).setCheckState(Qt.Checked)


def test_reload_does_not_fire_the_change_signal(tab, qtbot) -> None:
    """Перечитывание списка — не действие пользователя.

    Пункты при этом расставляются программно, и без защиты каждый из них
    выглядел бы как щелчок галкой: набор баз переписывался бы сам собой.
    """
    widget, conn = tab
    widget.list.item(0).setCheckState(Qt.Checked)
    before = project_mod.get_tm_sources(conn)

    fired = []
    widget.sourcesChanged.connect(lambda: fired.append(1))
    widget.reload()
    assert fired == []
    assert project_mod.get_tm_sources(conn) == before


# --- нижняя полоса ---------------------------------------------------------


def test_the_status_counts_what_is_attached(tab) -> None:
    widget, _conn = tab
    widget.list.item(0).setCheckState(Qt.Checked)
    assert "1" in widget.status_text()


def test_a_database_gone_from_disk_is_still_listed(tab, bdd) -> None:
    """Включённая база пропала с диска — сказать об этом, а не промолчать.

    Молча выкинуть её из списка значило бы, что подсказки пропали, а почему —
    неизвестно.
    """
    widget, conn = tab
    _root, out = bdd
    widget.list.item(0).setCheckState(Qt.Checked)

    # Отцепляем перед удалением: подключённый файл Windows держит, и просто так
    # он не удалится. В жизни это и есть та самая последовательность — проект
    # закрыли, базу унесли, проект открыли снова. Список включённых при этом
    # живёт в самом проекте и отцепление его не трогает.
    project_mod.attach_tm_sources(conn, [])
    out.unlink()
    widget.reload()

    assert out.name in item_names(widget)
    assert widget.list.item(0).checkState() == Qt.Checked

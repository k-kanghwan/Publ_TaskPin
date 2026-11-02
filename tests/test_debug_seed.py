from datetime import datetime

import pytest

from manager import os_win, paths, todo_pages, todo_store, todo_trash, widget_config
from tools import debug_seed

NOW = datetime(2026, 11, 2, 10, 0)


@pytest.fixture
def seed_env(temp_db, tmp_path, monkeypatch):
    """임시 DB + 임시 config.json (실제 데이터 경로는 건드리지 않음)"""
    monkeypatch.setattr(paths, "data_path", lambda name: str(tmp_path / name))
    return tmp_path


def _page_items(name):
    page = next(p for p in todo_pages.load() if p["name"] == name)
    return [i for i in todo_store.load_todos() if i["page_id"] == page["id"]]


def test_ensure_creates_every_page_once(seed_env):
    made = debug_seed.ensure(NOW, check_dir=False)
    assert made == [name for name, _ in debug_seed.PAGES]
    assert debug_seed.ensure(NOW, check_dir=False) == []  # 이미 있으면 그대로

    for name in made:
        items = _page_items(name)
        assert items[0]["text"] == debug_seed.CHECK_TITLE  # 맨 위에 체크리스트
        assert items[0]["tag"] == "red"
        assert any(i["parent_id"] == items[0]["id"] for i in items)
        ids = {i["id"] for i in items}
        assert all(i["parent_id"] is None or i["parent_id"] in ids for i in items)

    cfg = widget_config.load_config()
    assert cfg["always_on_top"] is True
    assert cfg["todo_page"] == todo_pages.load()[1]["id"]  # 첫 예제 페이지 ("페이지 1" 다음)
    assert any(t["name"] == debug_seed.CUSTOM_TAG[0] for t in widget_config.custom_tags(cfg))


def test_examples_cover_data_features(seed_env):
    debug_seed.ensure(NOW, check_dir=False)
    now = NOW.astimezone()

    reminders = _page_items(f"{debug_seed.PREFIX}리마인더·검색")
    dues = [todo_store.due_at(i) for i in reminders if not i["done"]]
    assert any(d and d < now for d in dues)  # 지연
    assert any(d and d.date() == now.date() and d > now for d in dues)  # 오늘
    assert any(d and d.date() > now.date() for d in dues)  # 예정
    assert not any(todo_store.is_due(i, now) for i in reminders)  # 시작하자마자 팝업 없음

    tree = _page_items(f"{debug_seed.PREFIX}계층·접기")
    assert any(i["collapsed"] for i in tree)
    display = _page_items(f"{debug_seed.PREFIX}태그·표시")
    assert {i["tag"] for i in display} >= set(todo_store.TAGS)
    assert any(todo_store.is_separator(i["text"]) for i in display)

    assert any("보관된" in i["text"] for i in todo_store.load_archived())
    assert [e["item"]["text"] for e in todo_trash.recent(10)[0]["entries"]] == [
        "지운 예제 1",
        "지운 예제 2",
    ]


def test_deleted_page_comes_back_and_reset(seed_env):
    debug_seed.ensure(NOW, check_dir=False)
    name = f"{debug_seed.PREFIX}대량 150"
    page = next(p for p in todo_pages.load() if p["name"] == name)
    todo_pages.remove(page["id"])
    assert debug_seed.ensure(NOW, check_dir=False) == [name]
    assert widget_config.load_config()["todo_page"] != page["id"]

    before = len(todo_store.load_todos())
    debug_seed.reset(NOW, check_dir=False)
    assert len(todo_store.load_todos()) == before
    names = [p["name"] for p in todo_pages.load()]
    assert len(names) == len(set(names))  # 예제 페이지가 겹치지 않음


def test_refuses_real_data_dir(seed_env, monkeypatch):
    monkeypatch.setattr(os_win, "user_data_dir", lambda: r"C:\Users\x\AppData\Roaming\TaskPin")
    assert not debug_seed.is_debug_data()
    assert debug_seed.ensure(NOW) == []
    assert [p["name"] for p in todo_pages.load()] == ["페이지 1"]

    monkeypatch.setattr(
        os_win, "user_data_dir", lambda: r"C:\repo\.debug_appdata\TaskPin"
    )
    assert debug_seed.is_debug_data()

import os
import sqlite3
from datetime import datetime

from manager import db, paths, task_store, todo_pages, todo_store, todo_trash

NOW = datetime(2026, 10, 29, 18, 30, 5)


def _fill():
    items = [todo_store.new_item(text) for text in ("a", "b")]
    todo_store.save_todos(items)
    todo_trash.record(
        [{"item": items[0], "parent_id": None, "before_id": None, "child_ids": []}]
    )
    todo_pages.add("페이지 2")
    start = datetime(2026, 10, 29, 9, 0).astimezone()
    task_store.register("업무", "", start, start)


def _count(path, table):
    with sqlite3.connect(path) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_reset_all_backs_up_then_wipes(temp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "data_path", lambda name: str(tmp_path / name))
    _fill()

    backup = db.reset_all(NOW)
    assert os.path.basename(backup) == "taskpin-backup-20261029-183005.db"
    # 백업은 지우기 전 그대로
    assert _count(backup, "todos") == 2
    assert _count(backup, "todo_pages") == 2
    assert _count(backup, "tasks") == 1

    # 지금 DB 는 비고 첫 페이지만 남는다 (번호도 처음부터)
    assert todo_store.load_todos() == []
    assert todo_trash.recent(10) == []
    assert task_store.latest() is None
    assert todo_pages.load() == [{"id": 1, "name": "페이지 1"}]
    assert todo_pages.add("새")["id"] == 2
    with sqlite3.connect(backup) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 9


def test_reset_all_keeps_data_when_backup_fails(temp_db, tmp_path, monkeypatch):
    # 백업 경로가 폴더라 열 수 없으면 지우지 않는다
    monkeypatch.setattr(paths, "data_path", lambda name: str(tmp_path))
    _fill()
    try:
        db.reset_all(NOW)
    except sqlite3.Error:
        pass
    else:
        raise AssertionError("백업 실패가 그대로 올라와야 한다")
    assert len(todo_store.load_todos()) == 2

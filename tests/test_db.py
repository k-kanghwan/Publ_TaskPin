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
    # 백업 이름에 프로필(DB 파일 이름)을 넣는다
    assert os.path.basename(backup) == "taskpin-backup-test-20261029-183005.db"
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
        assert c.execute("PRAGMA user_version").fetchone()[0] == db._MIGRATIONS[-1][0]


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


def test_meta_is_per_db(temp_db, tmp_path):
    assert db.get_meta("todo_page") is None
    db.set_meta("todo_page", "3")
    db.set_meta("todo_page", "4")  # 같은 키는 덮어쓴다
    assert db.get_meta("todo_page") == "4"
    assert db.path() == str(temp_db)

    other = tmp_path / "other.db"
    db.connect(str(other))
    assert db.get_meta("todo_page", "없음") == "없음"  # DB(프로필)마다 따로
    db.connect(str(temp_db))
    assert db.get_meta("todo_page") == "4"


def test_conn_reopens_last_db_after_close(temp_db):
    db.set_meta("k", "v")
    db.close()
    assert db.get_meta("k") == "v"  # 닫은 뒤에 부르면 마지막 DB 를 다시 연다


def test_init_and_check_file(temp_db, tmp_path):
    new = tmp_path / "new.db"
    db.init_file(str(new))
    db.check_file(str(new))  # 이 앱의 DB
    with sqlite3.connect(new) as c:
        assert c.execute("SELECT name FROM todo_pages").fetchall() == [("페이지 1",)]
    try:
        db.init_file(str(new))
    except FileExistsError:
        pass
    else:
        raise AssertionError("있는 파일은 덮어쓰지 않아야 한다")

    other = tmp_path / "other.db"
    with sqlite3.connect(other) as c:
        c.execute("CREATE TABLE notes (x)")
    garbage = tmp_path / "garbage.db"
    garbage.write_text("이건 DB 가 아니다", encoding="utf-8")
    for path, error in ((other, ValueError), (garbage, sqlite3.DatabaseError)):
        try:
            db.check_file(str(path))
        except error:
            pass
        else:
            raise AssertionError(f"{path.name} 는 열면 안 된다")

import sqlite3
from datetime import datetime

from manager import db, task_store


def dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()


def test_no_task(temp_db):
    assert task_store.latest() is None
    assert task_store.current_task(dt("2026-10-23 09:00")) is None


def test_register_returns_latest(temp_db):
    task_store.register("first", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    second = task_store.register("", dt("2026-10-23 10:00"), dt("2026-10-23 11:30"))

    assert second is not None
    assert task_store.latest() == second
    assert task_store.latest().title == ""


def test_today_task_is_current_even_after_end(temp_db):
    task = task_store.register("t", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    assert task_store.current_task(dt("2026-10-23 09:30")) == task
    assert task_store.current_task(dt("2026-10-23 18:00")) == task  # +초과 시간 표시


def test_task_ended_yesterday_is_not_current(temp_db):
    task_store.register("t", dt("2026-10-22 09:00"), dt("2026-10-22 10:00"))
    assert task_store.current_task(dt("2026-10-23 08:00")) is None


def test_task_crossing_midnight_is_current_until_end(temp_db):
    task = task_store.register("night", dt("2026-10-22 23:30"), dt("2026-10-23 01:00"))
    assert task_store.current_task(dt("2026-10-23 00:30")) == task
    assert task_store.current_task(dt("2026-10-23 01:30")) is None


def test_clear_hides_task_but_keeps_record(temp_db):
    task = task_store.register("t", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    assert task_store.clear(task.id)

    assert task_store.latest() is None
    assert task_store.current_task(dt("2026-10-23 09:30")) is None
    with sqlite3.connect(temp_db) as c:
        row = c.execute(
            "SELECT title, cleared_at FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
    assert row[0] == "t" and row[1]


def test_register_after_clear_is_shown(temp_db):
    first = task_store.register("a", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    task_store.clear(first.id)
    second = task_store.register("b", dt("2026-10-23 10:00"), dt("2026-10-23 11:00"))
    assert task_store.latest() == second


def test_v1_db_is_migrated(tmp_path):
    """v0.1.0 에서 만든 DB(cleared_at 없음)도 열리고 기존 Task 가 그대로 보인다."""
    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as c:
        c.executescript(db._SCHEMA_V1)
        c.execute(
            "INSERT INTO tasks (title, start_at, end_at, created_at)"
            " VALUES ('old', '2026-10-23 09:00', '2026-10-23 10:00', '2026-10-23 08:55:00')"
        )
    db.connect(str(path))
    try:
        latest = db._MIGRATIONS[-1][0]
        assert db.conn().execute("PRAGMA user_version").fetchone()[0] == latest
        assert task_store.latest().title == "old"
    finally:
        db.close()

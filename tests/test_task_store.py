import sqlite3
from datetime import datetime

from manager import db, task_store


def dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()


def test_no_task(temp_db):
    assert task_store.latest() is None
    assert task_store.current_task(dt("2026-10-23 09:00")) is None


def test_register_returns_latest(temp_db):
    task_store.register("first", "", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    second = task_store.register("", "", dt("2026-10-23 10:00"), dt("2026-10-23 11:30"))

    assert second is not None
    assert task_store.latest() == second
    assert task_store.latest().title == ""


def test_detail_is_saved(temp_db):
    task = task_store.register(
        "회의", "자료 정리\n- 1안 비교", dt("2026-10-23 09:00"), dt("2026-10-23 10:00")
    )
    assert task.detail == "자료 정리\n- 1안 비교"
    assert task_store.latest() == task


def test_today_task_is_current_even_after_end(temp_db):
    task = task_store.register("t", "", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    assert task_store.current_task(dt("2026-10-23 09:30")) == task
    assert task_store.current_task(dt("2026-10-23 18:00")) == task  # +초과 시간 표시


def test_task_ended_yesterday_is_not_current(temp_db):
    task_store.register("t", "", dt("2026-10-22 09:00"), dt("2026-10-22 10:00"))
    assert task_store.current_task(dt("2026-10-23 08:00")) is None


def test_task_crossing_midnight_is_current_until_end(temp_db):
    task = task_store.register(
        "night", "", dt("2026-10-22 23:30"), dt("2026-10-23 01:00")
    )
    assert task_store.current_task(dt("2026-10-23 00:30")) == task
    assert task_store.current_task(dt("2026-10-23 01:30")) is None


def test_clear_hides_task_but_keeps_record(temp_db):
    done = task_store.register("t", "", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    assert task_store.clear(done.id, task_store.COMPLETED)
    assert task_store.latest() is None
    assert task_store.current_task(dt("2026-10-23 09:30")) is None

    released = task_store.register(
        "r", "", dt("2026-10-23 10:00"), dt("2026-10-23 11:00")
    )
    assert task_store.clear(released.id, task_store.RELEASED)
    assert task_store.latest() is None

    with sqlite3.connect(temp_db) as c:
        rows = c.execute(
            "SELECT title, cleared_at, cleared_as FROM tasks ORDER BY id"
        ).fetchall()
    assert [(r[0], bool(r[1]), r[2]) for r in rows] == [
        ("t", True, "completed"),
        ("r", True, "released"),
    ]


def test_update_edits_same_row(temp_db):
    task = task_store.register("t", "", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    edited = task_store.update(
        task.id, "고침", "메모", dt("2026-10-23 09:30"), dt("2026-10-23 11:00")
    )
    assert edited.id == task.id
    assert task_store.latest() == edited
    with sqlite3.connect(temp_db) as c:
        assert c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1


def test_v5_cleared_rows_become_completed(tmp_path):
    path = tmp_path / "v5.db"
    with sqlite3.connect(path) as c:
        c.executescript(
            db._SCHEMA_V1
            + db._SCHEMA_V2
            + db._SCHEMA_V3
            + db._SCHEMA_V4
            + db._SCHEMA_V5
        )
        c.execute(
            "INSERT INTO tasks (title, start_at, end_at, created_at, cleared_at)"
            " VALUES ('old', '2026-10-23 09:00', '2026-10-23 10:00', 'x', 'y')"
        )
        c.execute(
            "INSERT INTO tasks (title, start_at, end_at, created_at)"
            " VALUES ('now', '2026-10-23 10:00', '2026-10-23 11:00', 'x')"
        )
    c.close()
    db.connect(str(path))
    try:
        rows = db.conn().execute("SELECT cleared_as FROM tasks ORDER BY id").fetchall()
        assert [r[0] for r in rows] == ["completed", None]
        assert task_store.latest().title == "now"
    finally:
        db.close()


def test_register_after_clear_is_shown(temp_db):
    first = task_store.register("a", "", dt("2026-10-23 09:00"), dt("2026-10-23 10:00"))
    task_store.clear(first.id, task_store.COMPLETED)
    second = task_store.register(
        "b", "", dt("2026-10-23 10:00"), dt("2026-10-23 11:00")
    )
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
        assert task_store.latest().detail == ""
    finally:
        db.close()

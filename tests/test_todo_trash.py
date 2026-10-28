import sqlite3

from manager import db, todo_store, todo_trash


def _entry(text, parent_id=None, before_id=None, child_ids=()):
    item = todo_store.new_item(text)
    return {
        "item": item,
        "parent_id": parent_id,
        "before_id": before_id,
        "child_ids": list(child_ids),
    }


def test_record_and_recent_newest_first(temp_db):
    first = [_entry("a", child_ids=["x"]), _entry("b", before_id="c")]
    second = [_entry("d")]
    assert todo_trash.record(first) == 1
    assert todo_trash.record(second) == 2
    assert todo_trash.record([]) is None

    batches = todo_trash.recent(10)
    assert [b["batch"] for b in batches] == [2, 1]
    assert [e["item"]["text"] for e in batches[1]["entries"]] == ["a", "b"]
    assert batches[1]["entries"][0]["child_ids"] == ["x"]
    assert batches[1]["entries"][1]["before_id"] == "c"
    assert batches[1]["entries"][0]["item"] == first[0]["item"]  # 스냅샷 그대로


def test_recent_limit_counts_restored_batches(temp_db):
    for text in "abc":
        todo_trash.record([_entry(text)])
    todo_trash.mark_restored(3)
    # 최근 2번의 삭제(3, 2) 중 되돌리지 않은 것만 - 1 은 범위 밖
    assert [b["batch"] for b in todo_trash.recent(2)] == [2]
    assert [b["batch"] for b in todo_trash.recent(5)] == [2, 1]

    with sqlite3.connect(temp_db) as c:  # 이력 행은 남아 있다
        assert c.execute("SELECT COUNT(*) FROM todo_deletions").fetchone()[0] == 3
    c.close()


def test_recent_skips_broken_rows(temp_db):
    todo_trash.record([_entry("a"), _entry("b")])
    with sqlite3.connect(temp_db) as c:
        c.execute("UPDATE todo_deletions SET snapshot = 'broken' WHERE id = 1")
    c.close()
    entries = todo_trash.recent(5)[0]["entries"]
    assert [e["item"]["text"] for e in entries] == ["b"]


def test_migrate_v7_adds_deletions(tmp_path):
    path = tmp_path / "v7.db"
    with sqlite3.connect(path) as c:
        c.executescript(
            "".join(script for version, script in db._MIGRATIONS if version <= 7)
        )
    c.close()

    db.connect(str(path))
    try:
        assert db.conn().execute("PRAGMA user_version").fetchone()[0] >= 8
        assert todo_trash.recent(5) == []
        assert todo_trash.record([_entry("a")]) == 1
    finally:
        db.close()

import sqlite3

from manager import db, todo_store


def _items(*texts):
    return [todo_store.new_item(text) for text in texts]


def _archived_rows(path):
    with sqlite3.connect(path) as c:
        return c.execute(
            "SELECT id, archived_at FROM todos WHERE archived_at IS NOT NULL"
        ).fetchall()


def test_save_then_load_keeps_order(temp_db):
    items = _items("a", "b (@2026-10-23 09:00)", "c")
    items[1]["done"] = True
    items[2]["snooze_until"] = "2026-10-23 10:00"
    todo_store.save_todos(items)

    loaded = todo_store.load_todos()
    assert [item["id"] for item in loaded] == [item["id"] for item in items]
    assert loaded == items  # dict 키 / 값(bool done 포함) 그대로


def test_reorder_is_saved(temp_db):
    items = _items("a", "b", "c")
    todo_store.save_todos(items)
    todo_store.save_todos([items[2], items[0], items[1]])

    assert [item["text"] for item in todo_store.load_todos()] == ["c", "a", "b"]


def test_removed_item_is_deleted(temp_db):
    items = _items("a", "b")
    todo_store.save_todos(items)
    todo_store.save_todos(items[:1])

    assert [item["text"] for item in todo_store.load_todos()] == ["a"]
    with sqlite3.connect(temp_db) as c:
        assert c.execute("SELECT COUNT(*) FROM todos").fetchone()[0] == 1


def test_archived_items_leave_list_but_stay_in_db(temp_db):
    items = _items("a", "b", "c")
    items[1]["done"] = True
    todo_store.save_todos(items)

    # TodoPanel.clear_done 순서: 보관 -> 목록에서 빼고 저장
    todo_store.archive_items([items[1]["id"]])
    remaining = [item for item in items if not item["done"]]
    todo_store.save_todos(remaining)

    assert [item["text"] for item in todo_store.load_todos()] == ["a", "c"]
    archived = _archived_rows(temp_db)
    assert [row[0] for row in archived] == [items[1]["id"]]
    assert archived[0][1]

    # 이후 저장이 반복되어도 보관 행은 남는다
    todo_store.save_todos(remaining[:1])
    assert [row[0] for row in _archived_rows(temp_db)] == [items[1]["id"]]


def test_parent_id_is_saved(temp_db):
    items = _items("a", "b")
    items[1]["parent_id"] = items[0]["id"]
    todo_store.save_todos(items)
    assert [item["parent_id"] for item in todo_store.load_todos()] == [
        None,
        items[0]["id"],
    ]

    items[1]["parent_id"] = None
    todo_store.save_todos(items)
    assert todo_store.load_todos()[1]["parent_id"] is None


def test_migrate_v2_adds_parent_id(tmp_path):
    path = tmp_path / "v2.db"
    with sqlite3.connect(path) as c:
        c.executescript(db._SCHEMA_V1 + db._SCHEMA_V2)
        c.execute(
            "INSERT INTO todos (id, text, done, position) VALUES ('x', 'old', 0, 0)"
        )
    c.close()

    db.connect(str(path))
    try:
        latest = db._MIGRATIONS[-1][0]
        assert db.conn().execute("PRAGMA user_version").fetchone()[0] == latest
        loaded = todo_store.load_todos()
        assert [(item["id"], item["parent_id"]) for item in loaded] == [("x", None)]
    finally:
        db.close()


def test_tag_is_saved_and_invalid_tag_dropped(temp_db):
    items = _items("a", "b", "c")
    items[0]["tag"] = "blue"
    items[1]["tag"] = "custom-1a2b3c4d"  # 사용자 태그 키도 그대로
    todo_store.save_todos(items)
    assert [item["tag"] for item in todo_store.load_todos()] == [
        "blue",
        "custom-1a2b3c4d",
        None,
    ]

    with sqlite3.connect(temp_db) as c:
        c.execute("UPDATE todos SET tag = ? WHERE id = ?", ("x" * 65, items[0]["id"]))
        c.execute("UPDATE todos SET tag = '' WHERE id = ?", (items[1]["id"],))
    c.close()
    assert [item["tag"] for item in todo_store.load_todos()] == [None, None, None]


def test_migrate_v3_adds_tag(tmp_path):
    path = tmp_path / "v3.db"
    with sqlite3.connect(path) as c:
        c.executescript(db._SCHEMA_V1 + db._SCHEMA_V2 + db._SCHEMA_V3)
        c.execute(
            "INSERT INTO todos (id, text, done, position) VALUES ('x', 'old', 0, 0)"
        )
    c.close()

    db.connect(str(path))
    try:
        assert [item["tag"] for item in todo_store.load_todos()] == [None]
    finally:
        db.close()


def test_reminder_token_helpers_unchanged():
    assert (
        todo_store.strip_reminder("회의자료 (@2026-10-21 09:00) 준비")
        == "회의자료 준비"
    )
    assert (
        todo_store.parse_reminder("날짜만 (@2026-10-21)").strftime("%H:%M") == "09:00"
    )


def test_to_html_wraps_emoji_runs():
    style = "font-size:14px;"
    html = todo_store.to_html("배포 🚀 <b>👨‍👩‍👧 ok ❤️</b> (@2026-10-23 09:00)", style)
    span = f'<span style="{style}">'
    assert html == (
        f"배포 {span}🚀</span> &lt;b&gt;{span}👨‍👩‍👧</span> ok {span}❤️</span>&lt;/b&gt;"
    )
    # 스타일을 주지 않으면 그대로
    assert todo_store.to_html("a 🚀") == "a 🚀"


def test_to_html_marks_spans():
    mark = '<span style="background-color:#80f5cc45">'
    text = "a<b 🚀 c (@2026-10-23 09:00)"
    html = todo_store.to_html(text, marks=[(1, 3)], mark_style="background-color:#80f5cc45")
    assert html == f"a{mark}&lt;b</span> 🚀 c"
    # 표시 구간 안의 이모지도 감싼다
    html = todo_store.to_html(text, "x;", [(4, 5)], "m;")
    assert html == 'a&lt;b <span style="m;"><span style="x;">🚀</span></span> c'


def test_collapsed_roundtrip(temp_db):
    items = [todo_store.new_item("a"), todo_store.new_item("b")]
    items[0]["collapsed"] = True
    todo_store.save_todos(items)
    loaded = {i["text"]: i["collapsed"] for i in todo_store.load_todos()}
    assert loaded == {"a": True, "b": False}

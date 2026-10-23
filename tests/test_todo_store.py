import sqlite3

from manager import todo_store


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


def test_reminder_token_helpers_unchanged():
    assert todo_store.strip_reminder("회의자료 (@2026-10-21 09:00) 준비") == "회의자료 준비"
    assert todo_store.parse_reminder("날짜만 (@2026-10-21)").strftime("%H:%M") == "09:00"

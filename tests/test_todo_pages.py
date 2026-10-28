import sqlite3

from manager import db, todo_pages, todo_store


def test_first_page_comes_from_migration(temp_db):
    assert todo_pages.load() == [{"id": 1, "name": "페이지 1"}]


def test_add_rename_reorder_remove(temp_db):
    second = todo_pages.add("업무")
    third = todo_pages.add("개인")
    assert [page["name"] for page in todo_pages.load()] == ["페이지 1", "업무", "개인"]

    todo_pages.rename(second["id"], "회사")
    todo_pages.reorder([third["id"], 1, second["id"]])
    assert [page["name"] for page in todo_pages.load()] == ["개인", "페이지 1", "회사"]

    todo_pages.remove(third["id"])
    assert [page["id"] for page in todo_pages.load()] == [1, second["id"]]


def test_load_recreates_a_page_when_empty(temp_db):
    todo_pages.remove(1)
    pages = todo_pages.load()
    assert [page["name"] for page in pages] == ["페이지 1"]


def test_next_name_and_clean_name():
    pages = [{"name": "페이지 1"}, {"name": "업무"}, {"name": "페이지 7"}]
    assert todo_pages.next_name(pages) == "페이지 8"
    assert todo_pages.next_name([{"name": "업무"}]) == "페이지 1"
    assert todo_pages.clean_name("  회의   준비 ", "x") == "회의 준비"
    assert todo_pages.clean_name("   ", "x") == "x"
    assert len(todo_pages.clean_name("가" * 50, "x")) == todo_pages.NAME_MAX


def test_page_id_roundtrip(temp_db):
    page = todo_pages.add("업무")
    items = [todo_store.new_item("a"), todo_store.new_item("b", page["id"])]
    todo_store.save_todos(items)
    assert [item["page_id"] for item in todo_store.load_todos()] == [1, page["id"]]


def test_migrate_v8_puts_todos_on_first_page(tmp_path):
    path = tmp_path / "v8.db"
    with sqlite3.connect(path) as c:
        c.executescript(
            "".join(script for version, script in db._MIGRATIONS if version <= 8)
        )
        c.execute(
            "INSERT INTO todos (id, text, done, position) VALUES ('x', 'old', 0, 0)"
        )
    c.close()

    db.connect(str(path))
    try:
        assert db.conn().execute("PRAGMA user_version").fetchone()[0] >= 9
        assert [item["page_id"] for item in todo_store.load_todos()] == [1]
        assert todo_pages.load() == [{"id": 1, "name": "페이지 1"}]
    finally:
        db.close()

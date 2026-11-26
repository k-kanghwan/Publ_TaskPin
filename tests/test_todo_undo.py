"""되돌리기 / 다시 실행 (manager/todo_undo) - Qt 없음"""

from manager import todo_store, todo_undo

PAGES = [{"id": 1, "name": "페이지 1"}]


def _item(text, item_id, **fields):
    item = todo_store.new_item(text)
    item["id"] = item_id
    item.update(fields)
    return item


def _texts(items):
    return [item["text"] for item in items]


def test_no_change_no_step():
    items = [_item("a", "a"), _item("b", "b")]
    before = todo_undo.snapshot(items, PAGES)
    assert todo_undo.diff(before, items, PAGES) is None


def test_view_and_alarm_fields_are_not_steps():
    items = [_item("a", "a")]
    before = todo_undo.snapshot(items, PAGES)
    items[0]["collapsed"] = True
    items[0]["fired"] = "2026-01-01 09:00"
    items[0]["snooze_until"] = "2026-01-01 10:00"
    assert todo_undo.diff(before, items, PAGES) is None


def test_edit_undo_redo_keeps_unrelated_alarm_state():
    items = [_item("a", "a"), _item("b", "b")]
    before = todo_undo.snapshot(items, PAGES)
    items[0]["text"] = "a2"
    change = todo_undo.diff(before, items, PAGES)
    assert change["label"] == "수정"
    assert list(change["before"]) == ["a"]
    items[1]["fired"] = "2026-01-01 09:00"  # 그사이 알림 - 되돌려도 남는다

    undone = todo_undo.apply(change, items, todo_undo.BEFORE)
    assert _texts(undone) == ["a", "b"]
    assert undone[1]["fired"] == "2026-01-01 09:00"
    redone = todo_undo.apply(change, undone, todo_undo.AFTER)
    assert _texts(redone) == ["a2", "b"]


def test_add_and_delete_restore_order():
    items = [_item("a", "a"), _item("b", "b"), _item("c", "c")]
    before = todo_undo.snapshot(items, PAGES)
    del items[1]
    change = todo_undo.diff(before, items, PAGES)
    assert change["label"] == "삭제"
    assert _texts(todo_undo.apply(change, items, todo_undo.BEFORE)) == ["a", "b", "c"]

    before = todo_undo.snapshot(items, PAGES)
    items.append(_item("d", "d"))
    change = todo_undo.diff(before, items, PAGES)
    assert change["label"] == "추가"
    assert _texts(todo_undo.apply(change, items, todo_undo.BEFORE)) == ["a", "c"]


def test_reorder_and_field_labels():
    items = [_item("a", "a"), _item("b", "b")]
    before = todo_undo.snapshot(items, PAGES)
    items.reverse()
    change = todo_undo.diff(before, items, PAGES)
    assert change["label"] == "이동"
    assert _texts(todo_undo.apply(change, items, todo_undo.BEFORE)) == ["a", "b"]

    before = todo_undo.snapshot(items, PAGES)
    items[0]["done"] = True
    assert todo_undo.diff(before, items, PAGES)["label"] == "완료"
    before = todo_undo.snapshot(items, PAGES)
    items[0]["tag"] = "red"
    assert todo_undo.diff(before, items, PAGES)["label"] == "태그"
    before = todo_undo.snapshot(items, PAGES)
    items[0]["parent_id"] = "a"
    assert todo_undo.diff(before, items, PAGES)["label"] == "이동"


def test_page_changes_and_effects():
    items = [_item("a", "a")]
    before = todo_undo.snapshot(items, PAGES)
    pages = PAGES + [{"id": 2, "name": "페이지 2"}]
    change = todo_undo.diff(before, items, pages)
    assert change["label"] == "페이지 추가"
    assert change["pages_before"] == PAGES

    before = todo_undo.snapshot(items, pages)
    assert todo_undo.diff(before, items, [PAGES[0]])["label"] == "페이지 삭제"
    renamed = [{"id": 1, "name": "x"}, pages[1]]
    assert todo_undo.diff(before, items, renamed)["label"] == "페이지 이름"
    assert todo_undo.diff(before, items, pages[::-1])["label"] == "페이지 순서"

    # 부수효과만 있어도 한 걸음 (삭제 이력에서 되돌렸는데 항목이 안 돌아온 경우 등)
    effects = [(todo_undo.ARCHIVE, ("a",), False, True)]
    change = todo_undo.diff(before, items, pages, effects)
    assert change["effects"] == effects
    assert change["label"] == "완료 항목 정리"


def test_history_undo_redo_and_new_step_clears_redo():
    history = todo_undo.History(limit=2)
    assert history.undo_step() is None
    for label in ("1", "2", "3"):
        history.push({"label": label})
    assert history.undo_label() == "3"
    assert history.undo_step()["label"] == "3"
    assert history.undo_step()["label"] == "2"
    assert history.undo_step() is None  # 2개까지만 남김
    assert history.redo_label() == "2"
    assert history.redo_step()["label"] == "2"
    history.push({"label": "4"})
    assert history.redo_label() is None
    history.clear()
    assert history.undo_label() is None


def test_changed_ids_in_screen_order():
    items = [_item("a", "a"), _item("b", "b"), _item("c", "c")]
    before = todo_undo.snapshot(items, PAGES)
    items[2]["text"] = "c2"
    items[0]["text"] = "a2"
    del items[1]
    change = todo_undo.diff(before, items, PAGES)
    assert todo_undo.changed_ids(change) == ["a", "c", "b"]

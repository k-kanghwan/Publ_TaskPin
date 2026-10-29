from manager import todo_store, todo_tree


def _items(*specs):
    """specs: (text, 상위 text 또는 None) - id 는 text 로 둔다"""
    items = []
    for text, parent in specs:
        item = todo_store.new_item(text)
        item["id"] = text
        item["parent_id"] = parent
        items.append(item)
    return items


def _layout(items, sort_key=None):
    return [(item["id"], depth) for item, depth in todo_tree.flatten(items, sort_key)]


def _sort_key(item):
    # TodoPanel._sort_key 와 같은 규칙
    due = todo_store.due_at(item)
    return (item["done"], due is None, due.timestamp() if due else 0)


def test_flatten_puts_children_under_parent():
    items = _items(("a1", "a"), ("b", None), ("a", None), ("a1x", "a1"), ("a2", "a"))
    assert _layout(items) == [
        ("b", 0),
        ("a", 0),
        ("a1", 1),
        ("a1x", 2),
        ("a2", 1),
    ]


def test_flatten_sorts_within_siblings():
    items = _items(
        ("a", None),
        ("a1", "a"),
        ("a2 (@2026-10-23 09:00)", "a"),
        ("a3", "a"),
        ("b", None),
    )
    items[1]["done"] = True  # a1 완료 -> 형제 맨 뒤로
    assert _layout(items, _sort_key) == [
        ("a", 0),
        ("a2 (@2026-10-23 09:00)", 1),  # 리마인더는 형제 맨 위
        ("a3", 1),
        ("a1", 1),
        ("b", 0),
    ]


def test_detach_orphans_and_cycles():
    items = _items(("a", "gone"), ("b", "c"), ("c", "b"), ("d", "a"))
    assert todo_tree.detach_orphans(items)
    parents = {item["id"]: item["parent_id"] for item in items}
    assert parents["a"] is None  # 상위가 없음
    assert parents["d"] == "a"  # 상위는 멀쩡하므로 그대로
    # 순환은 하나만 끊으면 된다
    assert [parents["b"], parents["c"]].count(None) == 1
    assert not todo_tree.detach_orphans(items)


def test_move_into_child_keeps_subtree():
    items = _items(("a", None), ("b", None), ("b1", "b"))
    assert todo_tree.move(items, "b", "a", None)
    assert _layout(items) == [("a", 0), ("b", 1), ("b1", 2)]


def test_move_before_sibling_and_to_root_end():
    items = _items(("a", None), ("a1", "a"), ("a2", "a"), ("b", None))
    assert todo_tree.move(items, "a2", "a", "a1")
    assert _layout(items) == [("a", 0), ("a2", 1), ("a1", 1), ("b", 0)]

    assert todo_tree.move(items, "a1", None, None)
    assert _layout(items) == [("a", 0), ("a2", 1), ("b", 0), ("a1", 0)]

    assert not todo_tree.move(items, "a1", None, None)  # 이미 맨 뒤


def test_move_rejects_own_subtree():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"))
    assert not todo_tree.move(items, "a", "a1x", None)
    assert not todo_tree.move(items, "a", "a", None)
    assert not todo_tree.move(items, "a1", "a", "missing")
    assert _layout(items) == [("a", 0), ("a1", 1), ("a1x", 2)]


def test_move_undone_under_done_reopens_ancestors():
    items = _items(("a", None), ("a1", "a"), ("b", None))
    items[0]["done"] = items[1]["done"] = True
    assert todo_tree.move(items, "b", "a1", None)
    assert [item["done"] for item in items] == [False, False, False]


def test_set_done_propagates():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("a2", "a"))
    assert todo_tree.set_done(items, "a", True)
    assert all(item["done"] for item in items)

    # 하위 하나를 해제하면 그 상위들만 해제
    assert todo_tree.set_done(items, "a1x", False)
    done = {item["id"]: item["done"] for item in items}
    assert done == {"a": False, "a1": False, "a1x": False, "a2": True}

    assert not todo_tree.set_done(items, "a1x", False)

    # 상위를 해제하면 하위도 모두 해제
    assert todo_tree.set_done(items, "a", True)
    assert todo_tree.set_done(items, "a1", False)
    done = {item["id"]: item["done"] for item in items}
    assert done == {"a": False, "a1": False, "a1x": False, "a2": True}
    assert todo_tree.set_done(items, "a", False)
    assert not any(item["done"] for item in items)


def test_remove_promote_lifts_children_in_place():
    items = _items(("a", None), ("b", None), ("b1", "b"), ("b1x", "b1"), ("b2", "b"))
    # 목록에서 상위보다 앞에 있는 하위도 형제 순서(b2, b1)대로 지운 항목 자리에 온다
    items.insert(0, items.pop(4))
    assert todo_tree.remove_promote(items, "b")
    assert _layout(items) == [("a", 0), ("b2", 0), ("b1", 0), ("b1x", 1)]
    assert not todo_tree.remove_promote(items, "b")


def test_move_many_keeps_order():
    items = _items(("a", None), ("b", None), ("c", None), ("d", None))
    assert todo_tree.move_many(items, ["b", "d"], "a", None)
    assert _layout(items) == [("a", 0), ("b", 1), ("d", 1), ("c", 0)]

    assert todo_tree.move_many(items, ["b", "d"], None, "a")
    assert _layout(items) == [("b", 0), ("d", 0), ("a", 0), ("c", 0)]


def test_move_many_children_follow_selected_parent():
    items = _items(("a", None), ("a1", "a"), ("b", None))
    assert todo_tree.top_selected(items, ["a", "a1"]) == ["a"]
    assert todo_tree.move_many(items, ["a", "a1"], "b", None)
    assert _layout(items) == [("b", 0), ("a", 1), ("a1", 2)]


def test_move_many_rejects_own_bundle():
    items = _items(("a", None), ("b", None), ("b1", "b"))
    assert not todo_tree.move_many(items, ["a", "b"], "b1", None)
    assert not todo_tree.move_many(items, ["a", "b"], None, "b")
    assert not todo_tree.move_many(items, [], None, None)
    assert _layout(items) == [("a", 0), ("b", 0), ("b1", 1)]


def test_move_many_under_done_reopens_parent():
    items = _items(("a", None), ("b", None), ("c", None))
    items[0]["done"] = True
    assert todo_tree.move_many(items, ["b", "c"], "a", None)
    assert not items[0]["done"]


def test_flatten_hides_children_of_collapsed():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("b", None))
    items[0]["collapsed"] = True
    assert _layout(items) == [("a", 0), ("b", 0)]
    items[0]["collapsed"] = False
    items[1]["collapsed"] = True  # 중간만 접히면 손자만 숨는다
    assert _layout(items) == [("a", 0), ("a1", 1), ("b", 0)]


def test_flatten_ignores_collapsed_when_asked():
    items = _items(("a", None), ("a1", "a"))
    items[0]["collapsed"] = True
    assert [i["id"] for i, _ in todo_tree.flatten(items, hide_collapsed=False)] == [
        "a",
        "a1",
    ]


def test_set_collapsed_and_has_children():
    items = _items(("a", None), ("a1", "a"))
    assert todo_tree.has_children(items, "a")
    assert not todo_tree.has_children(items, "a1")
    assert todo_tree.set_collapsed(items, "a", True)
    assert not todo_tree.set_collapsed(items, "a", True)
    assert not todo_tree.set_collapsed(items, "none", True)


def test_set_all_collapsed_only_touches_parents():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("b", None))
    assert todo_tree.set_all_collapsed(items, True)
    assert [bool(item["collapsed"]) for item in items] == [True, True, False, False]
    assert not todo_tree.set_all_collapsed(items, True)
    assert todo_tree.set_all_collapsed(items, False)
    assert not any(item["collapsed"] for item in items)


def test_expand_ancestors():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"))
    items[0]["collapsed"] = items[1]["collapsed"] = True
    assert todo_tree.expand_ancestors(items, "a1x")
    assert not items[0]["collapsed"] and not items[1]["collapsed"]
    assert not todo_tree.expand_ancestors(items, "a1x")


def _delete(items, item_id):
    """TodoPanel._delete 와 같은 순서: 자리를 남기고 지운다"""
    info = todo_tree.removal(items, item_id)
    snapshot = dict(next(item for item in items if item["id"] == item_id))
    todo_tree.remove_promote(items, item_id)
    return snapshot, info


def _restore(items, snapshot, info):
    return todo_tree.restore(
        items, snapshot, info["parent_id"], info["before_id"], info["child_ids"]
    )


def test_removal_records_place():
    items = _items(("a", None), ("a1", "a"), ("a2", "a"), ("b", None))
    assert todo_tree.removal(items, "a") == {
        "parent_id": None,
        "before_id": "b",
        "child_ids": ["a1", "a2"],
    }
    assert todo_tree.removal(items, "a2")["before_id"] is None
    assert todo_tree.removal(items, "none") is None


def test_restore_puts_item_back_with_children():
    items = _items(("x", None), ("a", None), ("a1", "a"), ("a2", "a"), ("b", None))
    before = _layout(items)
    snapshot, info = _delete(items, "a")
    assert _layout(items) == [("x", 0), ("a1", 0), ("a2", 0), ("b", 0)]
    assert _restore(items, snapshot, info)
    assert _layout(items) == before
    assert not _restore(items, dict(snapshot), info)  # 이미 있는 id


def test_restore_many_in_reverse_order():
    # 상위와 하위를 함께 지웠다가 거꾸로 되돌리면 원래 계층으로
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("b", None))
    before = _layout(items)
    deleted = [_delete(items, "a"), _delete(items, "a1")]
    assert _layout(items) == [("a1x", 0), ("b", 0)]
    for snapshot, info in reversed(deleted):
        _restore(items, snapshot, info)
    assert _layout(items) == before


def test_restore_when_place_is_gone():
    items = _items(("p", None), ("a", "p"), ("a1", "a"), ("x", None))
    snapshot, info = _delete(items, "a")  # a1 은 p 아래로 올라감
    todo_tree.move(items, "a1", "x", None)  # 그 뒤 사용자가 다른 데로 옮김
    todo_tree.remove_promote(items, "p")
    assert _restore(items, snapshot, info)
    # 상위 p 가 없으니 최상위 맨 뒤, 옮겨 간 하위는 그대로
    assert _layout(items) == [("x", 0), ("a1", 1), ("a", 0)]


def test_restore_reopens_done_parent():
    items = _items(("p", None), ("c", "p"))
    snapshot, info = _delete(items, "c")
    todo_tree.set_done(items, "p", True)
    _restore(items, snapshot, info)
    assert not items[0]["done"]


# ==================================================
# 붙여넣기 / 구분선 자리 / 복사
# ==================================================
def test_next_sibling_id():
    items = _items(("a", None), ("a1", "a"), ("b", None), ("a2", "a"))
    assert todo_tree.next_sibling_id(items, "a") == "b"
    assert todo_tree.next_sibling_id(items, "a1") == "a2"
    assert todo_tree.next_sibling_id(items, "a2") is None
    assert todo_tree.next_sibling_id(items, "b") is None
    assert todo_tree.next_sibling_id(items, "없음") is None
    # 함께 옮겨질 형제는 건너뛴다
    assert todo_tree.next_sibling_id(items, "a", skip={"b"}) is None
    assert todo_tree.next_sibling_id(items, "a1", skip={"a1"}) == "a2"


def test_subtrees_keep_list_order_and_follow_parent():
    items = _items(("a", None), ("a1", "a"), ("b", None), ("a1x", "a1"), ("c", None))
    # a1 은 상위 a 를 따라간다
    result = todo_tree.subtrees(items, ["a1", "a", "c", "없음"])
    assert [item["id"] for item in result] == ["a", "a1", "a1x", "c"]
    assert result[0] is items[0]


def test_clone_relinks_parents_with_new_ids():
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("b", "z"))
    items[1]["done"] = True
    counter = iter(range(100))
    clones = todo_tree.clone(items, lambda: f"n{next(counter)}")
    assert [(c["id"], c["parent_id"]) for c in clones] == [
        ("n0", None),
        ("n1", "n0"),
        ("n2", "n1"),
        ("n3", None),  # 상위가 묶음 밖이면 맨 위
    ]
    assert clones[1]["done"] is True and clones[1]["text"] == "a1"
    # 원본은 그대로
    assert [(i["id"], i["parent_id"]) for i in items][3] == ("b", "z")
    assert clones[0] is not items[0]


def test_paste_target_keeps_level_up_to_one_below_anchor():
    # a(0) > a1(1) > a1x(2) / b(0)
    items = _items(("a", None), ("a1", "a"), ("a1x", "a1"), ("a2", "a"), ("b", None))
    # 같은 레벨: 바로 뒤 형제로
    assert todo_tree.paste_target(items, "a1", 1) == ("a", "a2")
    # 더 깊은 레벨(3레벨)을 1레벨 아래에: 한 단계 아래 = 첫 하위 앞
    assert todo_tree.paste_target(items, "a", 2) == ("a", "a1")
    assert todo_tree.paste_target(items, "a1x", 5) == ("a1x", None)  # 하위가 없으면 첫 하위로
    # 더 얕은 레벨: 그 레벨의 상위 바로 뒤로
    assert todo_tree.paste_target(items, "a1x", 0) == (None, "b")
    assert todo_tree.paste_target(items, "a1x", 1) == ("a", "a2")
    # 함께 옮겨질 항목은 건너뛴다 / 없는 기준은 최상위 맨 뒤
    assert todo_tree.paste_target(items, "a", 1, skip={"a1"}) == ("a", "a2")
    assert todo_tree.paste_target(items, "a1", 1, skip={"a2"}) == ("a", None)
    assert todo_tree.paste_target(items, None, 3) == (None, None)

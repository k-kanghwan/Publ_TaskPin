"""TODO 상위/하위 계층 (Qt 없음)

TodoPanel 의 평면 목록(todo_store 의 dict 리스트)에 그대로 적용한다. 변경 함수는 목록을 직접 고친다.
- item["parent_id"]: 상위 항목 id / None 이면 최상위
- 형제 사이 순서는 목록 안의 순서(= DB position)를 따른다. 형제가 아닌 항목과의 앞뒤는 의미가 없다.
- 완료된 상위의 하위는 모두 완료 상태로 둔다. (set_done / move 가 유지)
  그래서 "완료 항목 정리"는 완료 항목만 보관해도 묶음째 빠진다.
"""


def _find(items: list, item_id):
    return next((item for item in items if item["id"] == item_id), None)


def _in_cycle(by_id: dict, item: dict) -> bool:
    """상위를 따라 올라가다 자기 자신으로 돌아오는지"""
    seen = set()
    parent_id = item.get("parent_id")
    while parent_id is not None and parent_id in by_id and parent_id not in seen:
        if parent_id == item["id"]:
            return True
        seen.add(parent_id)
        parent_id = by_id[parent_id].get("parent_id")
    return False


def detach_orphans(items: list) -> bool:
    """상위가 목록에 없거나(삭제/보관됨) 상위 사슬이 순환하는 항목을 최상위로 올린다.

    Returns
    -------
    bool : 바뀐 항목이 있으면 True
    """
    by_id = {item["id"]: item for item in items}
    changed = False
    for item in items:
        parent_id = item.get("parent_id")
        if parent_id is None:
            continue
        if parent_id not in by_id or _in_cycle(by_id, item):
            item["parent_id"] = None
            changed = True
    return changed


def flatten(items: list, sort_key=None) -> list:
    """화면에 보일 순서로 펼친다. 하위는 상위 바로 밑에 붙고, 형제끼리만 sort_key 로 (안정) 정렬한다.

    Returns
    -------
    [(item, 레벨)] : 레벨은 최상위가 0
    """
    ids = {item["id"] for item in items}
    children = {}
    for item in items:
        parent_id = item.get("parent_id")
        children.setdefault(parent_id if parent_id in ids else None, []).append(item)

    result = []

    def visit(parent_id, depth):
        siblings = children.get(parent_id, [])
        if sort_key is not None:
            siblings = sorted(siblings, key=sort_key)
        for item in siblings:
            result.append((item, depth))
            visit(item["id"], depth + 1)

    visit(None, 0)
    return result


def descendants(items: list, item_id) -> list:
    """item_id 아래의 모든 하위 항목"""
    result = []
    seen = {item_id}
    stack = [item_id]
    while stack:
        parent_id = stack.pop()
        for item in items:
            if item.get("parent_id") == parent_id and item["id"] not in seen:
                seen.add(item["id"])
                result.append(item)
                stack.append(item["id"])
    return result


def ancestors(items: list, item_id) -> list:
    """item_id 의 상위 항목들 (바로 위 상위부터)"""
    by_id = {item["id"]: item for item in items}
    result = []
    seen = {item_id}
    item = by_id.get(item_id)
    while item is not None:
        parent = by_id.get(item.get("parent_id"))
        if parent is None or parent["id"] in seen:
            break
        seen.add(parent["id"])
        result.append(parent)
        item = parent
    return result


def set_done(items: list, item_id, done: bool) -> bool:
    """완료하면 하위도 모두 완료, 해제하면 상위도 모두 해제한다.

    Returns
    -------
    bool : 바뀐 항목이 있으면 True
    """
    item = _find(items, item_id)
    if item is None:
        return False
    related = descendants(items, item_id) if done else ancestors(items, item_id)
    changed = False
    for target in [item] + related:
        if target["done"] != done:
            target["done"] = done
            changed = True
    return changed


def move(items: list, item_id, parent_id, before_id) -> bool:
    """item_id 를 (하위 항목과 함께) parent_id 아래, before_id 앞으로 옮긴다.

    Parameters
    ----------
    parent_id : 새 상위 id / None 이면 최상위
    before_id : 이 형제 앞으로 / None 이면 형제들 맨 뒤로

    Returns
    -------
    bool : 바뀐 것이 있으면 True. 자기 자신이나 자기 하위 아래로는 옮기지 않는다.
    """
    item = _find(items, item_id)
    if item is None or item_id == before_id:
        return False
    if parent_id is not None and _find(items, parent_id) is None:
        return False
    subtree = [item] + descendants(items, item_id)
    if parent_id in {other["id"] for other in subtree}:
        return False
    before = _find(items, before_id) if before_id is not None else None
    if before_id is not None and (
        before is None or before.get("parent_id") != parent_id
    ):
        return False

    old = (item.get("parent_id"), items.index(item))
    items.remove(item)
    item["parent_id"] = parent_id
    items.insert(items.index(before) if before is not None else len(items), item)
    changed = old != (parent_id, items.index(item))

    # 완료된 상위 아래로 미완료 항목을 넣으면 상위를 다시 미완료로 (하위 해제 -> 상위 해제와 같은 규칙)
    if any(not other["done"] for other in subtree):
        for parent in ancestors(items, item_id):
            if parent["done"]:
                parent["done"] = False
                changed = True
    return changed


def top_selected(items: list, ids) -> list:
    """ids 중 상위가 함께 들어 있지 않은 것만 (상위를 옮기면 하위는 따라온다). ids 순서 유지"""
    chosen = set(ids)
    return [
        item_id
        for item_id in ids
        if not any(parent["id"] in chosen for parent in ancestors(items, item_id))
    ]


def move_many(items: list, ids: list, parent_id, before_id) -> bool:
    """여러 항목을 (각각 하위와 함께) parent_id 아래, before_id 앞으로 ids 순서대로 옮긴다.

    Parameters
    ----------
    ids : 옮길 항목 id 들 (화면 순서). 상위가 함께 들어 있는 항목은 상위를 따라간다.
    parent_id / before_id : move 와 같다

    Returns
    -------
    bool : 바뀐 것이 있으면 True. 옮기는 묶음 안으로는 옮기지 않는다 (아무것도 바꾸지 않음).
    """
    roots = [item_id for item_id in top_selected(items, ids) if _find(items, item_id)]
    if not roots:
        return False
    moving = set(roots)
    for item_id in roots:
        moving.update(other["id"] for other in descendants(items, item_id))
    if parent_id in moving or before_id in moving:
        return False

    changed = False
    for item_id in roots:
        changed = move(items, item_id, parent_id, before_id) or changed
    return changed


def remove_promote(items: list, item_id) -> bool:
    """항목 하나만 지우고, 바로 아래 하위들은 지운 항목의 상위로 올려 그 자리에 순서대로 둔다.

    Returns
    -------
    bool : 지웠으면 True
    """
    item = _find(items, item_id)
    if item is None:
        return False
    children = [other for other in items if other.get("parent_id") == item_id]
    child_ids = {child["id"] for child in children}
    for child in children:
        child["parent_id"] = item.get("parent_id")

    result = []
    for other in items:
        if other is item:
            result.extend(children)
        elif other["id"] not in child_ids:
            result.append(other)
    items[:] = result
    return True

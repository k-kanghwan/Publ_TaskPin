"""TODO 되돌리기 / 다시 실행 (Qt 없음)

TodoPanel 은 마지막으로 저장한 상태(snapshot)를 들고 있다가, 저장할 때마다 지금 상태와 비교해(diff)
바뀐 것을 한 걸음(change)으로 History 에 쌓는다. 그래서 할 일을 바꾸는 동작마다 따로 기록하지 않아도
추가 / 수정 / 삭제 / 체크 / 이동 / 태그 / 붙여넣기 / 정리 / 페이지 변경이 모두 되돌려진다.

- 한 걸음은 바뀐 항목만 전 / 후 사본으로 남긴다 (나머지는 되돌릴 때 지금 dict 그대로 - 그사이 알림 기록 보존).
- 접기(collapsed) / 알림 기록(fired) / 미룬 시각(snooze_until)만 바뀐 것은 걸음으로 남기지 않는다 (보기 / 알림 상태).
- todos / todo_pages 밖의 DB 부수효과(삭제 이력 묶음, 보관)는 effects 로 (종류, 대상, 전 값, 후 값)을 남겨
  되돌리기는 전 값, 다시 실행은 후 값을 적용한다 (TodoPanel).
"""

IGNORED_FIELDS = ("collapsed", "fired", "snooze_until")
MAX_STEPS = 100  # 되돌릴 수 있는 걸음 수 (넘으면 오래된 것부터 버림)

# effects 종류
TRASH = "trash"  # 삭제 이력 묶음: 값 = 되돌릴 수 있는 상태인지 (True: 이력에 보임 / False: 되돌림 처리)
ARCHIVE = "archive"  # 완료 항목 정리: 값 = 보관됐는지

BEFORE = "before"
AFTER = "after"


def snapshot(items: list, pages: list) -> dict:
    """비교 기준: 항목 순서 + 항목 사본 + 페이지 [{"id", "name"}] 순서"""
    return {
        "order": [item["id"] for item in items],
        "items": {item["id"]: dict(item) for item in items},
        "pages": [{"id": page["id"], "name": page["name"]} for page in pages],
    }


def _core(item: dict) -> dict:
    """되돌릴 만한 필드만 (보기 / 알림 상태는 뺀다)"""
    return {key: value for key, value in item.items() if key not in IGNORED_FIELDS}


def _page_keys(pages: list) -> list:
    return [(page["id"], page["name"]) for page in pages]


def diff(before: dict, items: list, pages: list, effects=()):
    """before(snapshot) 이후 바뀐 것을 한 걸음으로. 바뀐 것이 없으면 None

    Returns
    -------
    {"before": {id: 전 사본 / None(없었음)}, "after": {id: 후 사본 / None(지워짐)},
     "order_before", "order_after": 항목 id 순서, "pages_before", "pages_after", "effects", "label"}
    """
    now = {item["id"]: item for item in items}
    old = before["items"]
    changed = [
        item_id
        for item_id in before["order"]
        if item_id not in now or _core(now[item_id]) != _core(old[item_id])
    ]
    changed += [item_id for item_id in now if item_id not in old]
    order_after = [item["id"] for item in items]
    common_after = [item_id for item_id in order_after if item_id in old]
    common_before = [item_id for item_id in before["order"] if item_id in now]
    reordered = common_after != common_before
    pages_after = [{"id": page["id"], "name": page["name"]} for page in pages]
    pages_changed = _page_keys(pages_after) != _page_keys(before["pages"])
    effects = list(effects)
    if not (changed or reordered or pages_changed or effects):
        return None
    change = {
        "before": {item_id: _copy(old.get(item_id)) for item_id in changed},
        "after": {item_id: _copy(now.get(item_id)) for item_id in changed},
        "order_before": list(before["order"]),
        "order_after": order_after,
        "pages_before": [dict(page) for page in before["pages"]],
        "pages_after": pages_after,
        "effects": effects,
    }
    change["label"] = label(change)
    return change


def _copy(item):
    return dict(item) if item is not None else None


def label(change: dict) -> str:
    """메뉴에 보일 이름 (무엇을 되돌리는지) - 바뀐 것으로 짐작한다"""
    kinds = {effect[0] for effect in change["effects"]}
    if ARCHIVE in kinds:
        return "완료 항목 정리"
    pages_before, pages_after = change["pages_before"], change["pages_after"]
    if _page_keys(pages_before) != _page_keys(pages_after):
        before_ids = {page["id"] for page in pages_before}
        after_ids = {page["id"] for page in pages_after}
        if after_ids - before_ids:
            return "페이지 추가"
        if before_ids - after_ids:
            return "페이지 삭제"
        if [p["id"] for p in pages_before] != [p["id"] for p in pages_after]:
            return "페이지 순서"
        return "페이지 이름"
    before, after = change["before"], change["after"]
    added = [i for i in after if before[i] is None]
    removed = [i for i in before if after[i] is None]
    if added and not removed:
        return "삭제 되돌리기" if TRASH in kinds else "추가"
    if removed and not added:
        return "삭제"
    fields = set()
    for item_id in before:
        if before[item_id] is not None and after[item_id] is not None:
            old, new = _core(before[item_id]), _core(after[item_id])
            fields |= {
                key for key in set(old) | set(new) if old.get(key) != new.get(key)
            }
    if "text" in fields:
        return "수정"
    if "done" in fields:
        return "완료"
    if "tag" in fields:
        return "태그"
    return "이동"


def apply(change: dict, items: list, side: str) -> list:
    """items 를 change 의 side(BEFORE 되돌리기 / AFTER 다시 실행) 상태로 만든 새 목록.
    바뀐 항목은 그쪽 사본으로(없던 항목은 빠지고 지운 항목은 돌아옴), 나머지는 지금 dict 그대로 그쪽 순서로."""
    states = change[side]
    order = change["order_" + side]
    now = {item["id"]: item for item in items}
    result, seen = [], set()
    for item_id in order:
        if item_id in states:
            state = states[item_id]
            if state is not None:
                result.append(dict(state))
                seen.add(item_id)
        elif item_id in now:
            result.append(now[item_id])
            seen.add(item_id)
    # 기록 밖에서 생긴 항목이 있으면 버리지 않고 맨 뒤에 둔다 (걸음은 LIFO 라 보통 없다)
    for item in items:
        if item["id"] not in seen and item["id"] not in states:
            result.append(item)
    return result


def changed_ids(change: dict) -> list:
    """이 걸음에서 바뀐 항목 id (전 / 후 순서를 합쳐 화면 순서에 가깝게)"""
    order = change["order_after"] + [
        item_id
        for item_id in change["order_before"]
        if item_id not in change["order_after"]
    ]
    return [item_id for item_id in order if item_id in change["before"]]


class History:
    """되돌리기 / 다시 실행 스택. 새 걸음이 오면 다시 실행 스택은 비운다."""

    def __init__(self, limit: int = MAX_STEPS):
        self._limit = limit
        self._undo = []
        self._redo = []

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def push(self, change: dict):
        self._undo.append(change)
        del self._undo[: -self._limit]
        self._redo.clear()

    def undo_label(self):
        """되돌릴 걸음의 이름 / 없으면 None"""
        return self._undo[-1]["label"] if self._undo else None

    def redo_label(self):
        return self._redo[-1]["label"] if self._redo else None

    def undo_step(self):
        """되돌릴 걸음을 꺼내 다시 실행 쪽으로 옮기고 돌려준다 (없으면 None)"""
        if not self._undo:
            return None
        change = self._undo.pop()
        self._redo.append(change)
        return change

    def redo_step(self):
        if not self._redo:
            return None
        change = self._redo.pop()
        self._undo.append(change)
        return change

"""TODO 검색 / 날짜별 보기 (우패널 Ctrl+F 막대)

- 날짜별 보기는 미완료 리마인더만 본다. 기준 시각은 todo_store.due_at(미룬 시각 우선) - 행에 표시되는 시각과 같다.
  - 지연: 시각이 지남 / 오늘: 오늘 안에 남음 / 예정: 내일 이후
- 검색은 리마인더 토큰을 뺀 본문에서 대소문자 구분 없이 찾는다. 공백으로 나눈 단어가 모두 들어 있어야 맞다.
- 조건에 맞는 항목의 상위는 트리 문맥으로 함께 보여준다 (조건에는 맞지 않는 "문맥" 항목).
"""

import re
from datetime import datetime

from manager import todo_store, todo_tree

VIEWS = ("all", "today", "overdue", "upcoming")
DATE_VIEWS = VIEWS[1:]


def bucket(item: dict, now: datetime):
    """날짜별 보기 칸 ("today" / "overdue" / "upcoming"). 완료했거나 리마인더가 없으면 None"""
    if item.get("done"):
        return None
    due = todo_store.due_at(item)
    if due is None:
        return None
    if due < now:
        return "overdue"
    if due.date() == now.date():
        return "today"
    return "upcoming"


def _words(query: str) -> list:
    return (query or "").casefold().split()


def matches(item: dict, query: str) -> bool:
    """검색어의 단어가 모두 본문(리마인더 토큰 제외)에 들어 있는지. 빈 검색어는 모두 맞다.
    구분선("---")은 검색어로는 걸리지 않는다 ("-" 를 찾을 때 구분선이 모두 맞지 않게)"""
    text = item.get("text", "")
    if todo_store.is_separator(text):
        return not _words(query)
    body = todo_store.strip_reminder(text).casefold()
    return all(word in body for word in _words(query))


def match_spans(body: str, query: str) -> list:
    """본문(리마인더 토큰을 뺀 문자열)에서 검색어 단어가 나오는 구간 [(시작, 끝)] (하이라이트용).
    겹치거나 붙은 구간은 하나로 합친다. 빈 검색어면 []"""
    spans = sorted(
        (m.start(), m.end())
        for word in _words(query)
        for m in re.finditer(re.escape(word), body, re.IGNORECASE)
    )
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def is_active(view: str, query: str) -> bool:
    """목록을 거르는 중인지 (전체 보기 + 빈 검색어면 아님)"""
    return view != "all" or bool(_words(query))


def _hit(item: dict, view: str, query: str, now: datetime) -> bool:
    return (view == "all" or bucket(item, now) == view) and matches(item, query)


def counts(items: list, query: str, now: datetime) -> dict:
    """날짜별 보기 칸마다 (검색어에도 맞는) 항목 수 {"today": n, "overdue": n, "upcoming": n}"""
    result = dict.fromkeys(DATE_VIEWS, 0)
    for item in items:
        key = bucket(item, now)
        if key is not None and matches(item, query):
            result[key] += 1
    return result


def visible(items: list, view: str, query: str, now: datetime):
    """보일 항목 id

    Returns
    -------
    (shown_ids, context_ids) : shown_ids 는 조건에 맞는 항목 + 그 상위 전부,
    context_ids 는 그중 조건에는 맞지 않지만 상위라서 보이는 항목
    """
    hits = {item["id"] for item in items if _hit(item, view, query, now)}
    context = set()
    for item_id in hits:
        context.update(parent["id"] for parent in todo_tree.ancestors(items, item_id))
    context -= hits
    return hits | context, context

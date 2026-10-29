"""TODO 내보내기 - Markdown 체크리스트 (Qt 없음)

하위 항목은 레벨마다 공백 2칸 들여쓴다(CommonMark / Obsidian 중첩 목록).
텍스트는 그대로 쓰므로 `(@YYYY-MM-DD HH:mm)` 리마인더 토큰도 obsidian-reminder 에서 그대로 읽힌다.
구분선 할 일은 Markdown 가로줄(---)로 쓴다.
"""

import re
from datetime import datetime

from manager import todo_store, todo_tree

TITLE = "Task알림 TODO"
STAMP_FMT = "%Y-%m-%d %H:%M"
# 파일 이름에 쓸 수 없는 글자 (Windows)
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _line(item: dict, level: int) -> str:
    indent = "  " * level
    if todo_store.is_separator(item["text"]):
        return indent + "---"
    return indent + ("- [x] " if item["done"] else "- [ ] ") + item["text"]


def _checklist(items: list) -> list:
    """[(item, 레벨)] 을 체크리스트 줄로. 접힌 항목의 하위도 모두 쓴다 (접힘은 화면 표시일 뿐)"""
    return [
        _line(item, level)
        for item, level in todo_tree.flatten(items, hide_collapsed=False)
    ]


def _header(subtitle: str, now: datetime) -> list:
    return [f"# {TITLE} — {subtitle}", f"내보낸 시각: {now.strftime(STAMP_FMT)}", ""]


def to_markdown(items: list, now: datetime, page_name: str = "") -> str:
    """화면 목록 (상위/하위 계층 그대로). page_name: 내보내는 페이지 이름 (제목에 넣는다)"""
    subtitle = f"{page_name} · 화면 목록" if page_name else "화면 목록"
    return "\n".join(_header(subtitle, now) + _checklist(items)) + "\n"


def to_text(items: list, sort_key=None) -> str:
    """클립보드용 Markdown 체크리스트 (`- [ ] 할 일`, 하위는 2칸 들여쓰기, 구분선은 ---).
    리마인더 토큰도 그대로 - Obsidian 등에 붙여넣으면 그대로 체크리스트가 된다."""
    return "\n".join(
        _line(item, level)
        for item, level in todo_tree.flatten(items, sort_key, hide_collapsed=False)
    )


def _with_ancestors(group: list, by_id: dict) -> list:
    """group 의 항목마다 상위 사슬을 앞에 붙인다 (이미 들어 있으면 한 번만).
    상위는 처음 나오는 하위의 자리에 놓이므로 최상위 순서는 group 순서를 따른다."""
    result, seen = [], set()
    for item in group:
        chain, chain_ids = [item], {item["id"]}  # 자기 자신부터 위로 (순환하면 멈춘다)
        parent = by_id.get(item.get("parent_id"))
        while parent is not None and parent["id"] not in chain_ids:
            chain.append(parent)
            chain_ids.add(parent["id"])
            parent = by_id.get(parent.get("parent_id"))
        for node in reversed(chain):  # 맨 위 상위부터
            if node["id"] not in seen:
                seen.add(node["id"])
                result.append(node)
    return result


def archived_to_markdown(items: list, now: datetime, active: list = ()) -> str:
    """보관 항목 전체. 보관 날짜별 섹션으로 나누고, 목록 순서(최근 보관 먼저)를 따른다.

    상위가 화면 목록에 남아 있거나(미완료) 다른 날짜에 보관됐어도 섹션마다 상위를 함께 쓴다.
    상위는 지금 체크 상태 그대로라, 하위가 다른 항목의 하위나 최상위처럼 보이지 않는다.
    active: 화면 목록 (보관하지 않은 상위를 찾는 데 쓴다)
    """
    by_id = {item["id"]: item for item in list(active) + list(items)}
    groups = {}
    for item in items:
        groups.setdefault((item.get("archived_at") or "")[:10], []).append(item)

    lines = _header("보관 항목", now)
    for day, group in groups.items():
        tree = _with_ancestors(group, by_id)
        lines += [f"## {day or '날짜 없음'} 보관", ""] + _checklist(tree) + [""]
    return "\n".join(lines).rstrip("\n") + "\n"


def filename_part(name: str) -> str:
    """파일 이름에 넣을 수 있게 고친 이름 (쓸 수 없는 글자는 _, 앞뒤 공백 / 마침표는 뺀다)"""
    return _UNSAFE_FILENAME_RE.sub("_", " ".join(name.split())).strip(" .")


def default_filename(archived: bool, now: datetime, page_name: str = "") -> str:
    """보관 항목은 모든 페이지라 페이지 이름을 넣지 않는다."""
    kind = "TODO-보관" if archived else "TODO"
    page = "" if archived else filename_part(page_name)
    if page:
        kind += f"-{page}"
    return f"TaskPin-{kind}-{now.strftime('%Y%m%d')}.md"

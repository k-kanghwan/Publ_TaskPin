"""TODO 내보내기 - Markdown 체크리스트 (Qt 없음)

하위 항목은 레벨마다 공백 2칸 들여쓴다(CommonMark / Obsidian 중첩 목록).
텍스트는 그대로 쓰므로 `(@YYYY-MM-DD HH:mm)` 리마인더 토큰도 obsidian-reminder 에서 그대로 읽힌다.
"""

from datetime import datetime

from manager import todo_tree

TITLE = "Task알림 TODO"
STAMP_FMT = "%Y-%m-%d %H:%M"


def _checklist(items: list) -> list:
    """[(item, 레벨)] 을 체크리스트 줄로"""
    return [
        "  " * level + ("- [x] " if item["done"] else "- [ ] ") + item["text"]
        for item, level in todo_tree.flatten(items)
    ]


def _header(subtitle: str, now: datetime) -> list:
    return [f"# {TITLE} — {subtitle}", f"내보낸 시각: {now.strftime(STAMP_FMT)}", ""]


def to_markdown(items: list, now: datetime) -> str:
    """화면 목록 (상위/하위 계층 그대로)"""
    return "\n".join(_header("화면 목록", now) + _checklist(items)) + "\n"


def archived_to_markdown(items: list, now: datetime) -> str:
    """보관 항목 전체. 보관 날짜별 섹션으로 나누고, 목록 순서(최근 보관 먼저)를 따른다.

    상위가 다른 섹션에 있거나 화면 목록에 남아 있으면 그 섹션의 최상위로 나온다.
    """
    groups = {}
    for item in items:
        groups.setdefault((item.get("archived_at") or "")[:10], []).append(item)

    lines = _header("보관 항목", now)
    for day, group in groups.items():
        lines += [f"## {day or '날짜 없음'} 보관", ""] + _checklist(group) + [""]
    return "\n".join(lines).rstrip("\n") + "\n"


def default_filename(archived: bool, now: datetime) -> str:
    kind = "TODO-보관" if archived else "TODO"
    return f"TaskPin-{kind}-{now.strftime('%Y%m%d')}.md"

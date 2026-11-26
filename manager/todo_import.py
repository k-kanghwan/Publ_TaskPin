"""TODO 가져오기 - Markdown 체크리스트 파일을 새 페이지의 할 일로 (Qt 없음)

앱이 내보낸 파일(manager/todo_export)과 사용자가 쓴 체크리스트(Obsidian 등)를 모두 읽는다.
- 목록 줄(`- [ ] 할 일`, `- [x] 한 일`, `- 메모`, `* 항목`, `1. 항목`)이 할 일이다. `[x]` / `[X]` 만 완료.
- 들여쓰기가 계층이다. 폭(2칸 / 4칸 / 탭)과 관계없이 바로 위의 덜 들여쓴 항목이 상위다.
- 하이픈(또는 * / _) 3개 이상인 줄은 구분선이다. 구분선은 하위를 두지 않는다.
- `#` 제목은 페이지 이름 후보, `## 이름` 은 SECTIONS 에서 새 페이지. 목록이 아닌 글자 줄은 건너뛴다.
- 맨 앞 YAML front matter(`---` ... `---`)는 건너뛴다.
"""

import os
import re
from datetime import datetime

from manager import todo_export, todo_pages, todo_store

# 가져오기 종류 (TodoPanel.import_requested -> ClockWidget._import_todos)
SINGLE = "single"  # 한 페이지로 (## 섹션은 무시)
SECTIONS = "sections"  # ## 섹션마다 새 페이지
MODES = (SINGLE, SECTIONS)
DEFAULT_NAME = "가져온 할 일"
MAX_BYTES = 2 * 1024 * 1024  # 이보다 큰 파일은 읽지 않는다 (체크리스트로는 충분히 큼)
TAB_WIDTH = 4

# 들여쓰기 / 목록 기호(- * + 1. 1)) / 체크박스(있으면) / 글자
_LIST_RE = re.compile(r"^( *)(?:[-*+]|\d+[.)])\s+(?:\[(.)\]\s*)?(.*)$")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_RULE_RE = re.compile(r"-{3,}|\*{3,}|_{3,}")
_FRONT_MATTER_END = ("---", "...")
# 앱이 내보낸 제목: "Task알림 TODO — 이름 · 현재 페이지" / "— 전체 페이지" / "— 보관 항목"
_APP_TITLE_RE = re.compile(rf"{re.escape(todo_export.TITLE)}\s+—\s+(.*)")
_APP_PAGE_SUFFIX = " · 현재 페이지"
# 앱이 내보낸 파일 이름: TaskPin-TODO-이름-YYYYMMDD (이름 없으면 TaskPin-TODO-YYYYMMDD)
_APP_FILENAME_RE = re.compile(r"TaskPin-TODO(?:-(.+))?-\d{8}")


def read_file(path: str) -> str:
    """파일 글자. UTF-8(BOM 있어도)로 읽고, 안 되면 cp949(메모장 ANSI 파일).
    OSError / 너무 크면 ValueError / 둘 다 안 되면 UnicodeDecodeError(ValueError 의 하위)."""
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"파일이 너무 큽니다 ({MAX_BYTES // (1024 * 1024)}MB 까지)")
    with open(path, "rb") as f:
        data = f.read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp949")


def page_name_from_file(path: str) -> str:
    """페이지 이름 후보: 확장자를 뺀 파일 이름. 앱이 내보낸 파일 이름이면 가운데 페이지 이름만."""
    stem = os.path.splitext(os.path.basename(path))[0].strip()
    match = _APP_FILENAME_RE.fullmatch(stem)
    if match:
        return match.group(1) or ""
    return stem


def _title_name(title: str) -> str:
    """# 제목 -> 페이지 이름 후보. 앱 제목이면 '현재 페이지' 의 이름만 (전체 / 보관은 후보 없음)"""
    match = _APP_TITLE_RE.fullmatch(title)
    if not match:
        return title
    subtitle = match.group(1)
    return subtitle[: -len(_APP_PAGE_SUFFIX)] if subtitle.endswith(_APP_PAGE_SUFFIX) else ""


def _skip_front_matter(lines: list) -> list:
    if not lines or lines[0].strip() != "---":
        return lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() in _FRONT_MATTER_END:
            return lines[idx + 1 :]
    return lines  # 닫는 줄이 없으면 front matter 가 아니다 (맨 앞 구분선)


class _Page:
    def __init__(self, name: str):
        self.name = name
        self.items = []
        self._stack = []  # [(들여쓰기, 항목)] - 상위가 될 수 있는 항목 (구분선은 넣지 않음)

    def add(self, indent: int, text: str, done: bool):
        while self._stack and self._stack[-1][0] >= indent:
            self._stack.pop()
        separator = todo_store.is_separator(text)
        item = todo_store.new_item(todo_store.SEPARATOR if separator else text, None)
        item["done"] = done and not separator
        item["parent_id"] = self._stack[-1][1]["id"] if self._stack else None
        self.items.append(item)
        if not separator:
            self._stack.append((indent, item))


def _fix_state(items: list, now: datetime) -> None:
    """완료 규칙: 미완료 할 일의 상위는 모두 미완료 (완료된 상위 => 하위도 모두 완료).
    구분선은 상위의 완료 상태를 따른다. 지난 리마인더는 알린 것으로 둔다 - 가져오자마자 팝업이 쏟아지지 않게."""
    by_id = {item["id"]: item for item in items}
    for item in items:
        if item["done"] or todo_store.is_separator(item["text"]):
            continue
        parent = by_id.get(item["parent_id"])
        while parent is not None and parent["done"]:
            parent["done"] = False
            parent = by_id.get(parent["parent_id"])
    for item in items:  # 문서 순서 = 상위가 먼저
        if todo_store.is_separator(item["text"]):
            parent = by_id.get(item["parent_id"])
            item["done"] = bool(parent and parent["done"])
        elif todo_store.is_due(item, now):
            item["fired"] = todo_store.due_key(todo_store.due_at(item))


def parse(text: str, mode: str = SINGLE, fallback_name: str = "", now=None) -> list:
    """Markdown 을 페이지 목록으로. 할 일이 없는(구분선뿐인) 페이지는 뺀다.

    Parameters
    ----------
    mode : SINGLE 한 페이지 / SECTIONS `## 이름` 마다 새 페이지 (첫 ## 앞의 할 일은 첫 페이지)
    fallback_name : 제목이 없을 때의 페이지 이름 (보통 page_name_from_file)
    now : 지난 리마인더를 가르는 기준 (기본 지금)

    Returns
    -------
    [{"name": 페이지 이름, "items": [할 일 dict]}] : 할 일은 문서 순서(상위가 하위보다 먼저),
        page_id 는 None - 넣는 쪽이 정한다.
    """
    now = now or datetime.now().astimezone()
    fallback = todo_pages.clean_name(fallback_name or "", DEFAULT_NAME)
    first = _Page("")
    pages = [first]
    title = None
    for raw in _skip_front_matter(text.splitlines()):
        line = raw.expandtabs(TAB_WIDTH).rstrip()
        heading = _HEADING_RE.match(line)
        if heading:
            level, name = len(heading.group(1)), heading.group(2)
            if level == 1 and title is None:
                title = _title_name(name)
            elif level == 2 and mode == SECTIONS:
                pages.append(_Page(todo_pages.clean_name(name, fallback)))
            continue
        page = pages[-1]
        stripped = line.strip()
        if _RULE_RE.fullmatch(stripped):
            page.add(len(line) - len(line.lstrip(" ")), todo_store.SEPARATOR, False)
            continue
        match = _LIST_RE.match(line)
        if not match:
            continue  # 목록이 아닌 글자 줄 / 빈 줄 / "내보낸 시각:"
        indent, box, body = match.groups()
        body = body.strip()
        if body:
            page.add(len(indent), body, box in ("x", "X"))
    first.name = todo_pages.clean_name(title or "", fallback)
    result = []
    for page in pages:
        if any(not todo_store.is_separator(item["text"]) for item in page.items):
            _fix_state(page.items, now)
            result.append({"name": page.name, "items": page.items})
    return result

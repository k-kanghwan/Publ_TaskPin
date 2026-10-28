"""바탕화면 위젯 설정 영속화 (%APPDATA%\\TaskPin\\config.json)

위젯 설정은 "없는 것이 정상"(첫 실행)이므로 파일이 없어도 예외를 던지지 않고 기본값을 돌려준다.
자동 실행 등록은 OS 의존 코드라 os_win 에 있다.
"""

import copy
import json
import os
import re
import uuid
from datetime import datetime

from manager import paths, snippets

CONFIG_NAME = "config.json"
EXPORT_PREFIX = "TaskPin-config"  # 설정 내보내기 파일 이름

# 위젯 단축키 (위젯 창이 활성일 때만 동작). 값은 QKeySequence PortableText, "" 이면 해제
DEFAULT_SHORTCUTS = {
    "task_register": "E",  # Task 등록 / 진행 중이면 해제 (좌패널 [등록/해제] 버튼)
    "task_edit": "R",  # Task 수정
    "task_clear": "C",  # Task 완료
    "todo_focus": "A",  # 할 일 입력칸으로 커서 이동
    "todo_edit": "F2",  # 선택한 할 일을 그 자리에서 수정
    "todo_search": "Ctrl+F",  # 할 일 검색 / 날짜별 보기 줄 열기
    "settings": "Ctrl+,",  # 설정 열기
}

# 설정창 Appearance 탭. 색은 "#rrggbb", "" 이면 테마를 따른다
THEMES = ("dark", "light", "system")
# 좌패널은 폭이 고정이라 크게 키우지 않는다
LEFT_SCALES = (90, 100, 115)
TODO_SCALES = (90, 100, 115, 130)
# 리마인더 알림 창 폭(px)과 글자 배율(%) - 높이는 내용에 맞춘다
POPUP_WIDTHS = (220, 260, 320, 380)
POPUP_SCALES = (90, 100, 115, 130)
DEFAULT_APPEARANCE = {
    "theme": "dark",
    "accent": "#4a7bd0",  # 강조색 (버튼 / 체크박스 / Task 배지 / 선택 표시)
    "background": "",  # 위젯 배경색
    "font_family": "",  # "" 이면 기본(맑은 고딕)
    "left_scale": 100,  # 좌패널 글자 배율(%)
    "todo_scale": 100,  # 우패널(TODO) 글자 배율(%)
    "todo_text_color": "",  # TODO 글자색
    "todo_strike": True,  # 완료한 할 일에 취소선
    "todo_row_lines": False,  # 할 일 행 사이 구분선
    "fade_text": False,  # 투명도 슬라이더가 글자까지 투명하게 할지 (False: 배경만)
    "popup_width": 260,  # 리마인더 알림 창 폭(px)
    "popup_scale": 100,  # 리마인더 알림 창 글자 배율(%)
}
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")

DEFAULT_CONFIG = {
    "pos": None,  # [x, y] / None 이면 우측 상단 배치
    "locked": False,  # 위치 잠금
    "visible": True,  # 위젯 표시 여부
    "opacity": 1.0,  # 위젯 불투명도 (0.2 ~ 1.0) - 슬라이더에는 투명도(1 - 값)로 표시
    "height": None,  # 세로 모드 높이(px) / None 이면 최소 높이
    "vertical_width": None,  # 세로 모드 폭(px) / None 이면 280 (1.3배까지)
    "width": None,  # 가로 모드 폭(px) / None 이면 최소 폭
    "horizontal_height": None,  # 가로 모드 높이(px) / None 이면 최소 높이 (최소의 1.5배까지)
    "orientation": "vertical",  # "vertical": 세로 / "horizontal": 가로(좌 시간, 우 TODO)
    "always_on_top": False,  # True: 항상 위 / False: 항상 아래(바탕화면)
    "user_name": "",  # 위젯 헤더에 표시할 사용자 이름 (더블클릭으로 편집)
    "shortcuts": DEFAULT_SHORTCUTS,  # 설정창 Keyboard Shortcuts 탭
    "snippets": snippets.DEFAULT_SNIPPETS,  # 설정창 Snippets 탭 [[":idea:", "💡"], ...]
    "appearance": DEFAULT_APPEARANCE,  # 설정창 Appearance 탭
    # 사용자가 추가한 TODO 태그 [{"id": "custom-…", "name": "Home", "color": "#rrggbb"}]
    # (우패널 태그 메뉴 "+ 태그 추가…" / 설정창 Appearance 에서 이름·색 변경, 삭제)
    "custom_tags": [],
}
CUSTOM_TAG_PREFIX = "custom-"  # 사용자 태그 id (todos.tag 에 저장되는 값)
CUSTOM_TAG_NAME_MAX = 20
# 기본값은 없지만 저장될 수 있는 키 (설정 가져오기에서도 받는다)
EXTRA_KEYS = ("export_dir",)  # TODO / 설정 내보내기 마지막 폴더


def load_config() -> dict:
    """위젯 설정을 읽어온다. 파일이 없거나 깨져있으면 기본값을 반환한다."""
    # 중첩된 dict/list 를 고쳐도 기본값이 바뀌지 않도록 깊은 복사
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(paths.data_path(CONFIG_NAME), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update(saved)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def shortcuts(cfg: dict) -> dict:
    """설정의 단축키. 빠졌거나 깨진 동작은 기본값으로 채운다."""
    saved = cfg.get("shortcuts")
    if not isinstance(saved, dict):
        saved = {}
    result = {}
    for action, default in DEFAULT_SHORTCUTS.items():
        value = saved.get(action, default)
        result[action] = value if isinstance(value, str) else default
    # 새로 생긴 동작의 기본 키가 사용자가 이미 다른 동작에 쓰는 키면 비워 둔다 (겹치지 않게)
    for action in DEFAULT_SHORTCUTS:
        if action not in saved and any(
            other != action and other in saved and result[other] == result[action]
            for other in result
        ):
            result[action] = ""
    return result


def custom_tags(cfg: dict) -> list:
    """사용자 태그 [{"id", "name", "color"}]. 깨진 항목 / 중복 id 는 뺀다."""
    saved = cfg.get("custom_tags")
    if not isinstance(saved, list):
        return []
    result, seen = [], set()
    for tag in saved:
        if not isinstance(tag, dict):
            continue
        tag_id, name = tag.get("id"), tag.get("name")
        color = _color(tag.get("color"), "")
        if (
            isinstance(tag_id, str)
            and tag_id.startswith(CUSTOM_TAG_PREFIX)
            and tag_id not in seen
            and color
        ):
            seen.add(tag_id)
            name = name.strip()[:CUSTOM_TAG_NAME_MAX] if isinstance(name, str) else ""
            result.append({"id": tag_id, "name": name or color, "color": color})
    return result


def add_custom_tag(cfg: dict, name: str, color: str) -> str:
    """사용자 태그를 cfg 에 추가하고 id 를 돌려준다. (저장은 부르는 쪽에서)"""
    tags = custom_tags(cfg)
    tag_id = f"{CUSTOM_TAG_PREFIX}{uuid.uuid4().hex[:8]}"
    tags.append(
        {"id": tag_id, "name": name.strip()[:CUSTOM_TAG_NAME_MAX], "color": color}
    )
    cfg["custom_tags"] = custom_tags({"custom_tags": tags})
    return tag_id


def _color(value, default: str) -> str:
    if isinstance(value, str) and _COLOR_RE.fullmatch(value):
        return value.lower()
    return default


def _bool(value, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _scale(value, steps: tuple, default: int = 100) -> int:
    # bool 은 int 의 하위 타입이고 100.0 == 100 이므로 정확히 int 만 받는다
    return value if type(value) is int and value in steps else default


def appearance(cfg: dict) -> dict:
    """설정의 Appearance 값. 빠졌거나 깨진 값은 기본값으로 채운다."""
    saved = cfg.get("appearance")
    if not isinstance(saved, dict):
        saved = {}
    default = DEFAULT_APPEARANCE
    theme = saved.get("theme")
    family = saved.get("font_family")
    return {
        "theme": theme if theme in THEMES else default["theme"],
        "accent": _color(saved.get("accent"), default["accent"]),
        "background": _color(saved.get("background"), ""),
        "font_family": family.strip() if isinstance(family, str) else "",
        "left_scale": _scale(saved.get("left_scale"), LEFT_SCALES),
        "todo_scale": _scale(saved.get("todo_scale"), TODO_SCALES),
        "todo_text_color": _color(saved.get("todo_text_color"), ""),
        "todo_strike": _bool(saved.get("todo_strike"), default["todo_strike"]),
        "todo_row_lines": _bool(saved.get("todo_row_lines"), default["todo_row_lines"]),
        "fade_text": saved.get("fade_text") is True,
        "popup_width": _scale(
            saved.get("popup_width"), POPUP_WIDTHS, default["popup_width"]
        ),
        "popup_scale": _scale(saved.get("popup_scale"), POPUP_SCALES),
    }


def _write(cfg: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)


def save_config(cfg: dict) -> None:
    """위젯 설정을 저장한다. 실패해도 앱 동작을 막지 않는다."""
    try:
        _write(cfg, paths.data_path(CONFIG_NAME))
    except OSError as e:
        print(f"위젯 설정 저장 실패: {e}")


# ==================================================
# 설정 내보내기 / 가져오기 (설정창 Application 탭)
# ==================================================
def export_config(cfg: dict, folder: str, now: datetime) -> str:
    """config.json 과 같은 내용을 folder 에 TaskPin-config-YYYYMMDD.json 으로 저장하고 경로를 돌려준다.
    같은 이름이 있으면 시각을 붙인다. 저장하지 못하면 OSError"""
    path = os.path.join(folder, f"{EXPORT_PREFIX}-{now:%Y%m%d}.json")
    if os.path.exists(path):
        path = os.path.join(folder, f"{EXPORT_PREFIX}-{now:%Y%m%d-%H%M%S}.json")
    _write(cfg, path)
    return path


def read_import(path: str):
    """내보낸 설정 파일을 읽어 기본값 위에 덮어쓴 새 설정을 돌려준다.
    알려진 키만 가져온다(값은 shortcuts / appearance 등 각 접근자가 바로잡음).
    읽지 못했거나 TaskPin 설정이 아니면(알려진 키가 하나도 없음) None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(saved, dict):
        return None
    known = {k: v for k, v in saved.items() if k in DEFAULT_CONFIG or k in EXTRA_KEYS}
    if not known:
        return None
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(known)
    return cfg

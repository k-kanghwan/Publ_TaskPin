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

# 위젯 단축키 (위젯 창이 활성일 때만 동작). 값은 QKeySequence PortableText, "" 이면 해제.
# 두 키까지 이어 누를 수 있다 ("G, G" = g 를 두 번)
DEFAULT_SHORTCUTS = {
    "task_register": "E",  # Task 등록 / 진행 중이면 해제 (좌패널 [등록/해제] 버튼)
    "task_edit": "R",  # Task 수정
    "task_clear": "C",  # Task 완료
    "todo_focus": "A",  # 할 일 입력칸으로 커서 이동
    # 선택한 할 일을 그 자리에서 수정. F2 는 고정 키로 늘 된다 (선택이 없으면 F2 는 페이지 이름 바꾸기)
    "todo_edit": "Return",
    # 목록 키 (LIST_SHORTCUTS): 할 일 목록에 포커스가 있을 때만 - 입력칸의 화살표는 그대로 둔다
    # 삭제 / 잘라내기 / 복사 / 붙여넣기 / 위 / 아래는 기본 키(Delete / Ctrl+X / Ctrl+C / Ctrl+V / ↑ / ↓)가
    # 고정 키로도 늘 동작한다 - 여기서 다른 키를 정하면 그 키도 함께 된다 (todo_panel.FIXED_NAV_KEYS)
    "todo_delete": "Del",  # 선택한 할 일 삭제
    "todo_cut": "Ctrl+X",  # 선택한 할 일 잘라내기 (붙여넣으면 옮겨진다)
    "todo_copy": "Ctrl+C",  # 선택한 할 일을 하위와 함께 복사
    "todo_paste": "Ctrl+V",  # 지금 행 아래에 붙여넣기
    "todo_up": "Up",  # 위 할 일 선택
    "todo_down": "Down",  # 아래 할 일 선택
    "todo_collapse": "Left",  # 펼친 상위면 접고, 아니면 상위로
    "todo_expand": "Right",  # 접힌 상위면 펴고, 펼쳤으면 첫 하위로
    "todo_first": "G, G",  # 맨 위 할 일 (vim 의 gg) - Home 은 고정 키로 따로 듣는다
    "todo_last": "Shift+G",  # 맨 아래 할 일 (vim 의 G) - End 도 고정
    "todo_search": "Ctrl+F",  # 할 일 검색 / 날짜별 보기 줄 열기
    "todo_page_prev": "Ctrl+PgUp",  # 할 일 이전 페이지 (엑셀 시트 이동과 같음)
    "todo_page_next": "Ctrl+PgDown",  # 할 일 다음 페이지
    "settings": "Ctrl+,",  # 설정 열기
}

# 창 단축키(QShortcut)가 아니라 할 일 목록이 직접 받는 키 (TodoPanel.set_nav_keys)
LIST_SHORTCUTS = (
    "todo_delete",
    "todo_cut",
    "todo_copy",
    "todo_paste",
    "todo_up",
    "todo_down",
    "todo_collapse",
    "todo_expand",
    "todo_first",
    "todo_last",
)

# 설정창 Appearance 탭. 색은 "#rrggbb", "" 이면 테마를 따른다
THEMES = ("dark", "light", "system")
# 좌패널은 폭이 고정이라 크게 키우지 않는다
LEFT_SCALES = (90, 100, 115)
TODO_SCALES = (90, 100, 115, 130)
# 리마인더 알림 창 폭(px)과 글자 배율(%) - 높이는 내용에 맞춘다
POPUP_WIDTHS = (220, 260, 320, 380)
POPUP_SCALES = (90, 100, 115, 130)
# TODO 페이지 표시(현재 이름 + 점) 위치 - 왼쪽 / 오른쪽은 점만 세로로
PAGE_BAR_POSITIONS = ("top", "bottom", "left", "right")
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
    "todo_guides": True,  # 하위 레벨 가이드 선 (상위의 접기 버튼에서 내려오는 강조색 세로선)
    "page_bar": "top",  # TODO 페이지 표시 위치 (PAGE_BAR_POSITIONS)
    "fade_text": False,  # 투명도가 글자까지 투명하게 할지 (False: 배경만)
    "popup_width": 260,  # 리마인더 알림 창 폭(px)
    "popup_scale": 100,  # 리마인더 알림 창 글자 배율(%)
}
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
# 우패널 "삭제 이력"으로 되돌릴 수 있는 최근 삭제 수 (설정창 Application)
UNDO_LIMITS = (5, 10, 20, 50)
DEFAULT_UNDO_LIMIT = 10
# 트레이 / 창 아이콘 (설정창 Application) - 첫 값이 기본. exe 아이콘은 빌드 때 정해져 바뀌지 않는다
APP_ICONS = ("dark", "light")
# 위젯 불투명도 (설정창 Appearance 투명도 슬라이더 - 값은 투명도 % = 100 - 불투명도 %)
OPACITY_MIN = 0.2  # 이보다 낮으면 위젯이 사라져 조작 불가
TRANSPARENCY_MAX = round((1 - OPACITY_MIN) * 100)  # 슬라이더 최대 투명도(%) = 80

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
    # 행의 ✕ 로 할 일을 지울 때 확인 창 (확인 창의 "다시 묻지 않음" -> False, 설정창 Application)
    "confirm_delete": True,
    "undo_limit": DEFAULT_UNDO_LIMIT,  # 되돌릴 수 있는 최근 삭제 수 (UNDO_LIMITS 중 하나)
    "todo_page": None,  # 마지막으로 본 TODO 페이지 id (없는 id 면 첫 페이지)
    "app_icon": APP_ICONS[0],  # 트레이 / 창 아이콘 (APP_ICONS 중 하나)
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


def opacity(cfg: dict) -> float:
    """위젯 불투명도 (OPACITY_MIN ~ 1.0). 깨진 값이면 1.0"""
    value = cfg.get("opacity", 1.0)
    if type(value) not in (int, float):  # bool 은 int 의 하위 타입이므로 정확히 숫자만
        value = 1.0
    return min(1.0, max(OPACITY_MIN, float(value)))


def transparency(cfg: dict) -> int:
    """투명도 슬라이더 값(%) = 100 - 불투명도 %"""
    return round((1 - opacity(cfg)) * 100)


def set_transparency(cfg: dict, percent: int) -> None:
    """투명도(%)를 불투명도로 저장한다 (기존 호환. 부동소수 오차 방지 round). 저장은 부르는 쪽에서"""
    percent = min(TRANSPARENCY_MAX, max(0, percent))
    cfg["opacity"] = round(1 - percent / 100, 2)


def confirm_delete(cfg: dict) -> bool:
    """행의 ✕ 로 지울 때 확인 창을 띄울지 (False 로 저장했을 때만 묻지 않는다)"""
    return cfg.get("confirm_delete") is not False


def undo_limit(cfg: dict) -> int:
    """되돌릴 수 있는 최근 삭제 수. 정해진 값이 아니면 기본값"""
    return _scale(cfg.get("undo_limit"), UNDO_LIMITS, DEFAULT_UNDO_LIMIT)


def app_icon(cfg: dict) -> str:
    """트레이 / 창 아이콘. 정해진 값이 아니면 기본값(다크)"""
    value = cfg.get("app_icon")
    return value if value in APP_ICONS else APP_ICONS[0]


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
        "todo_guides": _bool(saved.get("todo_guides"), default["todo_guides"]),
        "page_bar": (
            saved.get("page_bar")
            if saved.get("page_bar") in PAGE_BAR_POSITIONS
            else default["page_bar"]
        ),
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

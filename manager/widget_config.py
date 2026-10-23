"""바탕화면 위젯 설정 영속화 (%APPDATA%\\TaskPin\\config.json)

위젯 설정은 "없는 것이 정상"(첫 실행)이므로 파일이 없어도 예외를 던지지 않고 기본값을 돌려준다.
자동 실행 등록은 OS 의존 코드라 os_win 에 있다.
"""

import copy
import json
import re

from manager import paths, snippets

CONFIG_NAME = "config.json"

# 위젯 단축키 (위젯 창이 활성일 때만 동작). 값은 QKeySequence PortableText, "" 이면 해제
DEFAULT_SHORTCUTS = {
    "task_register": "E",  # Task 등록
    "task_clear": "C",  # Task 완료
    "todo_focus": "A",  # 할 일 입력칸으로 커서 이동
    "settings": "Ctrl+,",  # 설정 열기
}

# 설정창 Appearance 탭. 색은 "#rrggbb", "" 이면 테마를 따른다
THEMES = ("dark", "light", "system")
# 좌패널은 폭 / 가로 모드 높이가 고정이라 크게 키우지 않는다
LEFT_SCALES = (90, 100, 115)
TODO_SCALES = (90, 100, 115, 130)
DEFAULT_APPEARANCE = {
    "theme": "dark",
    "accent": "#4a7bd0",  # 강조색 (버튼 / 체크박스 / Task 배지 / 선택 표시)
    "background": "",  # 위젯 배경색
    "font_family": "",  # "" 이면 기본(맑은 고딕)
    "left_scale": 100,  # 좌패널 글자 배율(%)
    "todo_scale": 100,  # 우패널(TODO) 글자 배율(%)
    "todo_text_color": "",  # TODO 글자색
    "fade_text": False,  # 투명도 슬라이더가 글자까지 투명하게 할지 (False: 배경만)
}
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")

DEFAULT_CONFIG = {
    "pos": None,  # [x, y] / None 이면 우측 상단 배치
    "locked": False,  # 위치 잠금
    "visible": True,  # 위젯 표시 여부
    "opacity": 1.0,  # 위젯 불투명도 (0.2 ~ 1.0) - 슬라이더에는 투명도(1 - 값)로 표시
    "height": None,  # 세로 모드 높이(px) / None 이면 최소 높이 (좌우는 고정)
    "width": None,  # 가로 모드 폭(px) / None 이면 최소 폭 (상하는 고정)
    "orientation": "vertical",  # "vertical": 세로 / "horizontal": 가로(좌 시간, 우 TODO)
    "always_on_top": False,  # True: 항상 위 / False: 항상 아래(바탕화면)
    "user_name": "",  # 위젯 헤더에 표시할 사용자 이름 (더블클릭으로 편집)
    "shortcuts": DEFAULT_SHORTCUTS,  # 설정창 Keyboard Shortcuts 탭
    "snippets": snippets.DEFAULT_SNIPPETS,  # 설정창 Snippets 탭 [[":idea:", "💡"], ...]
    "appearance": DEFAULT_APPEARANCE,  # 설정창 Appearance 탭
}


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
    return result


def _color(value, default: str) -> str:
    if isinstance(value, str) and _COLOR_RE.fullmatch(value):
        return value.lower()
    return default


def _scale(value, steps: tuple) -> int:
    # bool 은 int 의 하위 타입이고 100.0 == 100 이므로 정확히 int 만 받는다
    return value if type(value) is int and value in steps else 100


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
        "fade_text": saved.get("fade_text") is True,
    }


def save_config(cfg: dict) -> None:
    """위젯 설정을 저장한다. 실패해도 앱 동작을 막지 않는다."""
    try:
        with open(paths.data_path(CONFIG_NAME), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except OSError as e:
        print(f"위젯 설정 저장 실패: {e}")

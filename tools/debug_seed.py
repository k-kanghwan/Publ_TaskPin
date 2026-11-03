"""디버그 실행용 데이터: .debug_appdata 를 디버그 실행마다 처음 상태로 새로 만든다 (Qt 없음)

TASKPIN_DEBUG=1 실행(TaskPinApp)이 단일 인스턴스를 확인한 뒤, 설정 / 프로필을 읽기 전에 prepare() 를 부른다.
데이터 폴더(.debug_appdata\\TaskPin)를 통째로 비우고 다시 만든다 - 지난 디버그에서 체크 / 수정 / 삭제한 것,
만든 프로필, 바꾼 설정, 초기화 백업, 내보낸 파일이 모두 사라진다. 창 자리(KEEP_CONFIG_KEYS)만 이어 받는다.

  - 기본 프로필(SEED_PROFILE): 기능마다 "🧪 ..." TODO 페이지(PAGES) + 진행 중인 Task(SEED_TASK)
  - 두 번째 프로필(PROFILE_B): 프로필 바꾸기를 시험할 자기 할 일 / 리마인더 / Task
  - 설정: 실제 앱의 config.json(real_config_path - 읽기만 하고 쓰지 않음)에서 시작해 테마 · 단축키 · 태그 등을
    바꾸지 않는다. DEBUG_CONFIG(프로필 / 위젯 보이기)와 내보내기 폴더(데이터 폴더 안 EXPORT_FOLDER)만 덮어쓴다.
    실제 설정이 없거나 깨졌으면 widget_config 기본값. 디버그에서만 바꿀 설정은 .debug_appdata\\debug_config.json
    (USER_CONFIG, 지우지 않음)에 적으면 맨 나중에 덮어쓴다.

환경변수 TASKPIN_DEBUG_KEEP=1 이면 있던 데이터로 이어서 실행한다 (비어 있으면 만든다). tools/dev_run 이
저장 시 재시작에 붙인다 - 시험하던 상태가 코드를 저장할 때마다 사라지지 않게. VS Code "디버그 (데이터 유지)"
구성도 이 값으로 껐다 켜도 남는 것(마지막 프로필 / 페이지)을 시험한다.

    python tools/debug_seed.py   # 앱을 띄우지 않고 .debug_appdata 만 새로 만들기 (디버그 앱은 끄고)

페이지마다 맨 위에 "✅ 확인할 것"(빨간 태그) 체크리스트를 두고, 구분선 아래에 시험할 예제 데이터를 둔다.
기능을 추가 / 변경하면 알맞은 페이지의 체크리스트와 예제를 함께 고친다 (CLAUDE.md "디버그 데이터").
빌드에는 들어가지 않는다 - TaskPin.py 는 importlib 로 불러 Nuitka 가 따라가지 않는다.
"""

import glob
import json
import os
import shutil
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if __name__ == "__main__":  # python tools/debug_seed.py
    sys.path.insert(0, ROOT)

from manager import (
    db,
    os_win,
    paths,
    profiles,
    task_clock,
    task_store,
    todo_pages,
    todo_store,
    todo_trash,
    widget_config,
)

DEBUG_DIR = ".debug_appdata"
KEEP_ENV = "TASKPIN_DEBUG_KEEP"  # "1" 이면 있던 데이터로 이어서 (tools/dev_run 의 저장 시 재시작)
PREFIX = "🧪 "
CHECK_TITLE = "✅ 확인할 것"
CUSTOM_TAG = ("🧪검토", "#8e7cc3")  # 예제용 사용자 태그 (이름, 색)
DELETED_TAG = "custom-deleted0"  # 설정에 없는 사용자 태그 - 태그 없음으로 보여야 함
SEED_PROFILE = profiles.DEFAULT_NAME  # 예제 페이지를 넣는 프로필 (디버그 앱이 처음 여는 프로필)
SEED_TASK = "🧪 기본 프로필 업무"
# 프로필 바꾸기 시험용 두 번째 프로필 (이모지 / 공백이 든 파일 이름)
PROFILE_B = "🧪 프로필 B"
PROFILE_B_TASK = "🧪 B 프로필 업무"
EXPORT_FOLDER = "exports"  # 데이터 폴더 안 - 시험으로 내보낸 파일이 실제 폴더에 쌓이지 않게
# 설정은 실제 앱의 config.json(real_config_path, 읽기만)에서 시작한다 - 테마 · 단축키 · 태그 · 글꼴 · 크기 등을
# 디버그가 바꾸지 않는다. 디버그 데이터와 맞춰야 하는 아래 값만 덮어쓴다 (export_dir 는 데이터 폴더의 exports).
DEBUG_CONFIG = {
    "profile": SEED_PROFILE,  # 예제를 넣은 프로필 (실제 프로필 이름은 디버그에 없음)
    "visible": True,  # 실제 앱에서 위젯을 숨겨 두었어도 디버그 위젯은 보이게
}
# 실제 설정 대신 지난 디버그 실행에서 이어 받는 설정 - 실제 위젯 자리와 겹치지 않게
KEEP_CONFIG_KEYS = ("pos",)


def is_debug_data() -> bool:
    """데이터 폴더가 .debug_appdata 안인지 (실제 %APPDATA%\\TaskPin 에는 절대 쓰거나 지우지 않는다)"""
    parts = os.path.normcase(os_win.user_data_dir()).replace("\\", "/").split("/")
    return os.path.normcase(DEBUG_DIR) in parts


def real_config_path() -> str:
    """실제 앱의 설정 파일 (%APPDATA% 를 바꿔도 실제 위치) - 디버그 설정의 바탕으로 읽기만 한다"""
    return os.path.join(os_win.real_user_data_dir(), widget_config.CONFIG_NAME)


def _base_config():
    """디버그 설정의 바탕: 실제 설정의 알려진 키만 기본값 위에 (설정 가져오기와 같은 widget_config.read_import).
    실제 설정이 없거나 깨졌으면 기본값. (설정, 실제 설정을 읽었는지)"""
    real = widget_config.read_import(real_config_path())
    return (real, True) if real is not None else (widget_config.load_config(), False)


# 사용자가 디버그에서만 바꾸고 싶은 설정 - .debug_appdata 바로 아래라 실행마다 지우는 TaskPin 폴더 밖이고 git 에도
# 들어가지 않는다. config.json 과 같은 모양으로 바꿀 키만 적는다. appearance / shortcuts 같은 묶음은 적은 항목만
# 바꾼다. 알려진 키만 쓰므로 "_설명" 같은 키는 메모로 둘 수 있다.
USER_CONFIG = "debug_config.json"


def user_config_path() -> str:
    return os.path.join(os.path.dirname(os_win.user_data_dir()), USER_CONFIG)


def _user_overrides():
    """디버그 설정 파일(USER_CONFIG)의 알려진 키. 파일이 없으면 {}, 읽지 못하거나 깨졌으면 None"""
    try:
        with open(user_config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    if not isinstance(saved, dict):
        return None
    known = set(widget_config.DEFAULT_CONFIG) | set(widget_config.EXTRA_KEYS)
    return {key: value for key, value in saved.items() if key in known}


def _apply_overrides(cfg: dict, overrides: dict) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key] = {**cfg[key], **value}  # 묶음은 적은 항목만
        else:
            cfg[key] = value


# ==================================================
# 페이지 내용
# ==================================================
# 노드: "글자" 또는 {"text", "done", "tag", "collapsed", "children", "fired", "snooze", "archive"}
#       / {"trash": [글자, ...]} (한 묶음으로 지운 할 일 - 삭제 이력)
def _token(dt: datetime) -> str:
    return todo_store.format_token(dt)


def _task_page(ctx):
    return [
        _check(
            f"좌패널에 진행 중인 Task '{SEED_TASK}' - 상세 업무가 3줄을 넘어 … + 툴팁 (세로 모드)",
            "가로 모드에서 위젯을 키우면 상세 업무가 더 많은 줄로 보임 (세로는 3줄)",
            "다음 15분 단위 시각(종료)이 지나면 남은시간이 +초과, 'Task 종료' 트레이 알림 1번",
            "[수정](R) → 'Task 수정' 제목, 종료를 미래로 바꾸면 종료 알림을 다시 받음",
            "[해제] 확인 버튼이 경고색 / [완료](C) 확인 창에 남은시간 표시 → 내리면 버튼이 '등록'으로",
            "[등록](E) 창에서 업무명을 비우면 확인 버튼이 꺼지고, Enter 를 누르면 경고 테두리",
            "업무명에 한글 입력 (조합 중인 글자도 확인 때 들어감), :rocket: → 🚀, Ctrl+Z 로 되돌아감",
            "시작 기본값 = 지금을 15분 단위로 올린 값 (06:36 → 06:45)",
            "상세 업무 칸 Enter = 줄바꿈, Ctrl+Enter = 확인 (어느 칸에서든)",
            "등록 창은 다른 앱을 눌러도 닫히지 않음 (취소 · Esc · 확인으로만)",
            "등록 창을 확인 없이 닫고 다시 [등록] → 업무명·상세가 남아 있음",
            "등록 창이 떠 있는 동안 위젯 클릭 → 등록 창이 앞으로, 위젯은 끌어 옮기기만",
            "위젯을 끌어 옮기면 열린 등록 창이 따라옴",
            "사용자 이름 더블클릭 편집 (좌패널에서 편집되는 곳은 여기뿐)",
            "위젯 버튼을 눌러도 글자 둘레에 점선 포커스 표시가 없음",
            "우클릭 '항상 위에 보이기' 켬 → 다른 앱을 눌러도 위젯이 위에 남음 (깜빡임 없음)",
            "'항상 위에 보이기' 끔 → 다른 앱을 누르면 바탕화면 층으로 내려감",
            "'항상 위에 보이기' 끔 상태에서 [등록] 창을 연 채 다른 앱 클릭 → 위젯·등록 창이 위에 남음,"
            " 창을 닫고 다른 앱을 누르면 바탕화면 층으로",
            "'항상 위에 보이기' 끔 상태에서 우클릭 내보내기 → 파일 창이 떠 있는 동안 위젯이 위에 남음",
            "우클릭 가로/세로 모드, 위치/크기 잠금(핸들 꺼짐), 위젯 숨기기 → 트레이로 다시 보이기",
            "하단 핸들 = 높이, 우측 핸들 = 폭 (모드마다 따로 저장)",
            "앱을 한 번 더 실행 → 경고 없이 기존 위젯이 앞으로 (디버그 데이터도 그대로)",
        ),
    ]


def _tree_page(ctx):
    return [
        _check(
            "꺾쇠(› / ⌄)로 접기·펼치기, ← → 키도 같음 (펼친 상위에서 ← = 접기, 아니면 상위로)",
            "우클릭 모두 접기 / 모두 펼치기",
            "'구현'을 펼치면 하위 마지막 행까지 보이게 스크롤",
            "하위 가이드 선이 꺾쇠 가운데에서 이어짐 (설정 '하위 가이드 선')",
            "형제 2 를 고르고 > → 형제 1 의 하위로, < → 다시 형제로",
            "행 가운데에 끌어 놓기 = 하위, 위/아래 1/3 = 그 자리 / Ctrl 누른 채 놓기 = 복사 (+ 배지)",
            "접힌 '구현 (접힘)' 가운데에 끌어 놓기 → 펼쳐지며 하위 맨 뒤로",
            "'완료된 상위' 하위 하나를 해제 → 상위도 해제 / 상위 체크 → 하위 모두 완료",
            "상위 삭제 → 하위가 한 단계 올라감",
            "클릭 / Ctrl+클릭 / Shift+클릭 선택, Space 로 모두 완료·해제",
            "G, G / Shift+G / Home / End 로 맨 위·맨 아래",
            "행을 고르고 메뉴 키 · Shift+F10 → 그 행 바로 아래에 우클릭 메뉴",
            "선택한 채 입력칸(A)에 입력 → 고른 항목의 하위 맨 뒤로 추가",
        ),
        "---",
        {
            "text": "프로젝트 A",
            "children": [
                {
                    "text": "설계",
                    "children": [
                        {"text": "화면 스케치", "children": ["4단계 깊이 항목"]},
                        "DB 스키마",
                    ],
                },
                {
                    "text": "구현 (접힘)",
                    "collapsed": True,
                    "children": [f"구현 하위 {n}" for n in range(1, 13)],
                },
                "배포",
            ],
        },
        {
            "text": "완료된 상위",
            "done": True,
            "children": [
                {"text": "완료된 하위 1", "done": True},
                {"text": "완료된 하위 2", "done": True},
            ],
        },
        *[f"형제 {n}" for n in range(1, 6)],
    ]


def _display_page(ctx):
    return [
        _check(
            "태그마다 체크박스 왼쪽 세로 막대 색이 다름, '태그 없음'은 막대 자리만 비움",
            "여러 개 고르고 우클릭 → 태그: 같은 태그면 그 칸에 강조색 테두리",
            "'+ 태그 추가…'로 사용자 태그 추가, 설정 Appearance 'TODO 태그'에서 이름·색 변경·삭제",
            "지운 사용자 태그 항목은 태그 없음으로 보임",
            "구분선은 더블클릭·F2 로 수정되지 않음, 하위로 끌어 넣을 수 없음",
            "우클릭 '아래에 구분선 추가'",
            "입력칸에서 Win+. 이모지 패널로 🚀 입력",
            "설정: 완료 항목 취소선 / 행 구분선 / 하위 가이드 선 켜고 끄기",
            "설정: 추천 테마·배경색을 바꾸면 글자색이 배경 색조를 띠고 읽을 수 있게 유지",
        ),
        "---",
        *[{"text": f"태그 {tag}", "tag": tag} for tag in todo_store.TAGS],
        {"text": f"사용자 태그 {CUSTOM_TAG[0]}", "tag": ctx.custom_tag()},
        {"text": "지운 사용자 태그 (태그 없음으로 보임)", "tag": DELETED_TAG},
        "태그 없음",
        "-----",
        {"text": "완료 항목 (취소선)", "done": True},
        "이모지 🚀 🐛 ✅ 💡 👍🏽 👨‍👩‍👧",
        "<b>꺾쇠</b> & 특수문자 <script> 가 글자 그대로 보임",
        (
            "아주 긴 할 일: 위젯 폭을 넘으면 여러 줄로 감싸져야 하고, 세로 모드에서 깊은 레벨이어도"
            " 글자가 잘리지 않고 다음 줄로 이어지는지 확인하는 예제 문장입니다."
        ),
    ]


def _reminder_page(ctx):
    now = ctx.now.replace(second=0, microsecond=0)
    overdue = now - timedelta(hours=2)
    # 자정 무렵이면 오늘 23:50 이 이미 지났으므로 5분 뒤로
    today = max(now.replace(hour=23, minute=50), now + timedelta(minutes=5))
    return [
        _check(
            "실행하고 약 2분 뒤 '곧 알림' 팝업 3개가 우측 상단에 쌓임 → 나중에 알림 / 완료 버튼",
            "가운데 팝업의 글자 부분 클릭 → 위젯이 열리고 그 할 일로 넘어가 행이 두 번 깜빡임,"
            " 그 팝업만 닫히고 아래 팝업이 위로 미끄러져 올라옴 (맨 위 팝업은 그대로)",
            "위젯을 숨긴 채(우클릭 위젯 숨기기) 팝업 클릭 → 위젯이 다시 보이며 그 할 일로",
            "맨 앞 고정 칩 '미완료'(알람 시계) → 모든 페이지의 날짜 있는 미완료가 시각 순, 행 끝에 '· 페이지 이름'",
            "미완료에서 체크 → 목록에서 빠짐 / 더블클릭 수정·태그·삭제는 됨 / 입력칸은 꺼짐",
            "미완료에서 드래그·잘라내기·붙여넣기·< >·구분선 추가·페이지로 이동은 안 됨 (메뉴도 꺼짐)",
            "미완료 행 우클릭 '원래 페이지에서 보기' → 그 페이지로 넘어가 접힌 상위가 펴지고 깜빡임",
            "미완료 칩 숫자 = 모은 할 일 수, 칩 우클릭 이름 바꾸기·옮기기·삭제는 꺼짐",
            "Ctrl+F → [전체][오늘][지연][예정] 칩 개수와 거른 목록",
            "검색 '사과 주스' → 두 단어가 모두 든 항목만, 맞는 글자 노란 배경이 2초 뒤 사라짐",
            "검색 'apple' → 대소문자 없이 'Apple' 도 맞음, 상위는 흐리게 함께 보임",
            "검색어를 둔 채 페이지를 넘기면 새 페이지에서 다시 거름 / 거르는 중에 할 일 추가 → 전체 보기로",
            "Esc → 검색어 지움, 한 번 더 Esc → 검색 줄 닫힘",
            "입력칸에 '(@' 입력 → 리마인더 날짜·시각 고르기 창",
            "리마인더 행 시각 앞의 알람 시계 아이콘: 지났으면 경고색, 완료면 흐림",
            "설정: 리마인더 알림 창 폭·글자 배율 → 미리보기와 실제 팝업 크기가 같음",
        ),
        "---",
        {
            "text": f"지연된 리마인더 {_token(overdue)}",
            "fired": todo_store.due_key(overdue.astimezone()),
        },
        f"오늘 남은 리마인더 {_token(today)}",
        f"예정 리마인더 (모레) {_token(now + timedelta(days=2))}",
        f"곧 알림 1 (2분 뒤) {_token(now + timedelta(minutes=2))}",
        f"곧 알림 2 (2분 뒤) {_token(now + timedelta(minutes=2))}",
        {
            "text": "접힌 상위 (미완료 → 원래 페이지에서 보기)",
            "collapsed": True,
            "children": [f"곧 알림 3 (2분 뒤, 접힌 하위) {_token(now + timedelta(minutes=2))}"],
        },
        {
            "text": f"나중에 알림으로 미룬 항목 {_token(overdue)}",
            "snooze": now + timedelta(minutes=30),
        },
        {"text": f"완료된 리마인더 {_token(overdue)}", "done": True},
        "사과 주스 사기",
        "사과 깎기",
        "바나나 주스",
        {"text": "과일 목록", "children": ["Apple pie 레시피", "apple 소문자"]},
    ]


def _edit_page(ctx):
    return [
        _check(
            "더블클릭 / F2 / Enter 로 그 자리 수정, 끝나면 ↑↓로 이어서 이동",
            "Ctrl+C → 다른 행에 Ctrl+V: 사본, 레벨을 지킴 (깊으면 한 단계 아래까지)",
            "Ctrl+X → 흐리게 → 다른 페이지에서 Ctrl+V 로 옮김 (Esc 로 취소)",
            "복사한 뒤 메모장에 붙여넣기 → Markdown 체크리스트 (- [ ], 2칸 들여쓰기, ---)",
            "Del / ✕ → 확인 창 '다시 묻지 않음' (설정 Application 에서 다시 켬), 지운 뒤 그 자리 행이 골라져 이어서 Del",
            "여러 개 고른 채 고른 행에서 우클릭 → 선택이 그대로라 태그·삭제가 한꺼번에",
            "우클릭 '삭제 이력' → '지운 예제' 묶음 되돌리기 (상위·자리 복원)",
            "우클릭 '완료 항목 정리 → 선택 항목' → 고른 완료 항목(하위 포함)만 보관으로",
            "'완료 항목 정리 → 이 페이지' → 이 페이지 완료 항목만 / 메뉴 괄호 안 개수",
            "'완료 항목 정리 → 모든 페이지…' → 경고색 확인 창에 '모든 페이지'·개수·페이지별 개수",
            "우클릭 내보내기 → 현재 페이지 (.md, 페이지 이름이 제목·파일명에, 기본 폴더는 디버그 데이터의 exports)",
            "내보내기 → 전체 페이지 → 페이지마다 '## 이름' 섹션 (TaskPin-TODO-전체-날짜.md)",
            "내보내기 → 보관 항목 전체 / 미완료 페이지에서 현재 페이지 → 원래 페이지별 섹션",
            "여러 개 고르고 우클릭 '페이지로 이동' → 대상 페이지 최상위 맨 뒤로",
        ),
        "---",
        {
            "text": "복사할 상위",
            "children": [{"text": "하위 A", "children": ["하위 A-1"]}, "하위 B"],
        },
        {"text": "붙여넣을 자리", "children": ["깊은 하위"]},
        {"text": "정리할 완료 항목 1", "done": True},
        {"text": "정리할 완료 항목 2", "done": True},
        {
            "text": "보관된 상위 (내보내기 '보관 항목')",
            "done": True,
            "archive": True,
            "children": [{"text": "보관된 하위", "done": True, "archive": True}],
        },
        {"trash": ["지운 예제 1", "지운 예제 2"]},
    ]


def _page_settings_page(ctx):
    return [
        _check(
            "페이지 칩이 넘침 → 지금 페이지가 보이게 밀리고 잘린 끝이 흐림",
            "칩 클릭 / 휠 / Ctrl+PgUp·PgDown 으로 넘기기 (끝에서 멈춤)",
            "Ctrl+Shift+PgUp → 맨 앞 '미완료', Ctrl+Shift+PgDown → 맨 뒤 페이지",
            "Ctrl+T → 맨 뒤에 새 페이지를 만들고 넘어감 (입력칸에서 쳐도 됨)",
            "F5 → 페이지 바로가기 창: 한글 검색(조합 중에도 거름) · ↑↓ · Enter 이동 · Esc 닫기, 클릭 이동",
            "칩 우클릭 '페이지 바로가기' → 모든 페이지(지금 페이지 체크, 할 일 수) 중 골라 이동",
            "칩 더블클릭 이름 바꾸기에서 ':idea:' → 💡 로 바뀜",
            "'미완료' 칩은 끌리지 않고, 다른 칩을 끌어도 그 앞으로 못 감",
            "칩을 끌어 순서 바꾸기 (Esc 로 취소), 칩 더블클릭으로 이름 바꾸기",
            "칩 뒤 숫자 = 체크 안 한 할 일 수 (하위 포함, 구분선 제외)",
            "우클릭 새 페이지 / 앞·뒤로 옮기기 / 삭제 (남은 할 일은 삭제 이력으로)",
            "설정 페이지 표시 위치: 위 / 아래 / 왼쪽 / 오른쪽 (왼쪽·오른쪽은 점만)",
            "설정창(Ctrl+,)을 닫았다 열면 마지막 탭부터",
            "추천 테마 드롭다운, 강조색·배경색, 투명도 슬라이더 + '글자도 함께 투명'",
            "드롭다운·슬라이더 위에서 휠 → 값이 바뀌지 않고 페이지만 스크롤",
            "폰트, 좌·우패널 글자 배율",
            "단축키 바꾸기: 두 키(G, G), 겹침 검사, ↶ 되돌리기 (페이지 그룹: 첫·마지막·새 페이지·바로가기)",
            "Snippets 탭에서 :트리거: 추가 → 할 일 입력에서 바뀜",
            "Application: 되돌릴 수 있는 삭제 수 (앱 아이콘은 디버그에서 늘 라임색 - 설치본에서 확인)",
            "설정 내보내기 → 값 바꾸기 → 가져오기 → 원래대로",
            "모든 데이터 초기화 (문구 입력해야 확인 켜짐) → 지금 프로필만 '페이지 1'로",
            "설정 · 단축키 · 태그가 실제 앱 설정 그대로 (체크리스트의 키는 기본 단축키 기준)",
            "설정·할 일을 바꾸고 트레이 '종료' → 디버그를 다시 실행(F5) → 설정은 실제 앱 설정으로, 할 일은 예제로"
            " (위젯 자리만 그대로) / 실제 앱의 설정은 바뀌지 않음",
        ),
    ]


def _profile_page(ctx):
    return [
        _check(
            "좌패널 우클릭 → '프로필 · 기본': 목록(지금 프로필 체크) · 새 프로필 · 다른 이름으로 저장"
            " · 이름 바꾸기 · 삭제 · 프로필 폴더 열기",
            "프로필이 둘 이상이면 이름 오른쪽에 프로필 칩 → 클릭하면 같은 메뉴, 트레이 툴팁에도 프로필 이름",
            f"'{PROFILE_B}'로 바꾸기 → 할 일 · 페이지 · 좌패널 Task('{SEED_TASK}' → '{PROFILE_B_TASK}')가"
            " 그 프로필 것으로",
            "다시 '기본'으로 → 마지막으로 보던 페이지가 열림 (페이지는 프로필마다 기억)",
            "할 일을 고치는 중(F2)에 프로필 칩 클릭 → 고친 글자가 원래 프로필에 저장됨",
            "할 일 복사(Ctrl+C) → 다른 프로필로 바꿔 붙여넣기(Ctrl+V) 됨 / 잘라내기(Ctrl+X)는 바꾸면 풀림",
            '새 프로필… → 이름에 \\ / : * ? " < > | 나 CON, 같은 이름(대소문자 무시)이면 빨간 안내 + 확인 꺼짐',
            "새 프로필 → '페이지 1'만 있는 빈 목록, Task 없음 (설정 · 태그 · 단축키는 그대로), 한 장이라 페이지 삭제 꺼짐",
            "다른 이름으로 저장… → 지금 내용 그대로인 새 프로필로 바뀜, 원래 프로필도 목록에 남음",
            "이름 바꾸기 → 프로필 폴더 열기로 파일 이름(이름.db)도 바뀐 것 확인, 대소문자만 바꾸기도 됨",
            "삭제… → '프로필 삭제'를 입력해야 켜짐, 지우면 목록 앞 프로필로 / 하나만 남으면 삭제 꺼짐",
            "프로필 폴더에 .db 를 복사해 넣으면 메뉴에 바로 보임, 텍스트 파일을 x.db 로 넣고 고르면 '열지 못했습니다'",
            "설정 → Application '모든 데이터 초기화' 설명에 지금 프로필 이름, 초기화해도 다른 프로필은 그대로",
            "트레이 '종료' 뒤 VS Code '디버그 (데이터 유지)'로 실행 → 마지막으로 연 프로필 · 페이지로 시작",
            f"그냥 디버그를 다시 실행하면 만든 프로필은 사라지고 지운 '{PROFILE_B}'는 다시 생김",
        ),
    ]


def _profile_b_page(ctx):
    now = ctx.now.replace(second=0, microsecond=0)
    return [
        _check(
            f"이 목록 · 페이지 · 좌패널 Task('{PROFILE_B_TASK}')는 '{PROFILE_B}' 프로필에만 있음",
            "헤더 오른쪽 프로필 칩 클릭 → '기본'으로 돌아가기",
            "아래 리마인더는 이 프로필을 연 동안에만 알림 (다른 프로필에서는 울리지 않음)",
            "'기본'에서 복사(Ctrl+C)한 할 일을 여기에 붙여넣기(Ctrl+V)",
        ),
        "---",
        f"B 프로필 리마인더 (3분 뒤) {_token(now + timedelta(minutes=3))}",
        {"text": "B 프로필 할 일", "children": ["B 프로필 하위"]},
    ]


def _bulk_page(ctx):
    nodes = []
    for n in range(1, 121):
        if n % 10 == 0:
            nodes.append(
                {
                    "text": f"대량 {n:03d} (하위 3)",
                    "collapsed": n % 20 == 0,
                    "children": [f"대량 {n:03d}-{k}" for k in range(1, 4)],
                }
            )
        else:
            nodes.append({"text": f"대량 {n:03d}", "done": n % 7 == 0})
    return [
        _check(
            "이 페이지로 처음 넘길 때·돌아올 때 끊김 없이 빠름",
            "↑↓ 길게 눌러 끝까지 이동, 화면 밖 행이 보이게 스크롤",
            "모두 접기 / 모두 펼치기 반응 속도",
            "행을 끌어 목록 위·아래 끝에 대면 계속 스크롤 (끄는 중에 휠도 됨)",
        ),
        "---",
        *nodes,
    ]


# (페이지 이름, 내용) - 기본 프로필에 이 순서로 만든다 (새 프로필의 "페이지 1" 뒤)
PAGES = (
    (f"{PREFIX}Task·위젯", _task_page),
    (f"{PREFIX}계층·접기", _tree_page),
    (f"{PREFIX}태그·표시", _display_page),
    (f"{PREFIX}리마인더·검색", _reminder_page),
    (f"{PREFIX}편집·이력", _edit_page),
    (f"{PREFIX}페이지·설정", _page_settings_page),
    (f"{PREFIX}프로필", _profile_page),
    (f"{PREFIX}대량 150", _bulk_page),
)


def _check(*steps) -> dict:
    return {"text": CHECK_TITLE, "tag": "red", "children": list(steps)}


# ==================================================
# Task (좌패널) - 등록 창처럼 15분 단위라 [수정] 창에 그대로 들어간다
# ==================================================
def _seed_task(now: datetime):
    """기본 프로필의 진행 중인 Task: 다음 15분 단위 시각에 끝난다 (+초과 / 종료 알림 시험)"""
    start = task_clock.floor_slot(now.astimezone()) - timedelta(minutes=45)
    detail = "\n".join(
        (
            "세로 모드에서는 상세 업무가 3줄까지 보임",
            "넘치면 끝이 … 이고 마우스를 올리면 툴팁에 전체",
            "가로 모드에서 위젯 높이를 키우면 더 많은 줄이 보임",
            "4번째 줄",
            "5번째 줄 (마지막)",
        )
    )
    return SEED_TASK, detail, start, start + timedelta(hours=1)


def _profile_b_task(now: datetime):
    start = task_clock.floor_slot(now.astimezone()) - timedelta(minutes=30)
    return PROFILE_B_TASK, f"{PROFILE_B} 프로필에만 있는 Task", start, start + timedelta(hours=2)


# (프로필 이름, 페이지들, Task) - 이 순서로 만든다. 페이지 이름이 None 이면 새 프로필의 "페이지 1"에 넣는다.
PROFILES = (
    (SEED_PROFILE, PAGES, _seed_task),
    (PROFILE_B, ((None, _profile_b_page),), _profile_b_task),
)


# ==================================================
# 만들기
# ==================================================
class _Builder:
    def __init__(self, page_id: int, now: datetime, cfg: dict):
        self.page_id = page_id
        self.now = now
        self.cfg = cfg
        self.items = []  # 목록 순서 (상위 다음에 하위)
        self.archive_ids = []
        self.trash = []  # todo_trash.record 항목

    def custom_tag(self) -> str:
        name, color = CUSTOM_TAG
        for tag in widget_config.custom_tags(self.cfg):
            if tag["name"] == name:
                return tag["id"]
        return widget_config.add_custom_tag(self.cfg, name, color)

    def add(self, node, parent_id=None):
        if isinstance(node, str):
            node = {"text": node}
        if "trash" in node:
            for text in node["trash"]:
                item = todo_store.new_item(text, self.page_id)
                self.trash.append(
                    {"item": item, "parent_id": None, "before_id": None, "child_ids": []}
                )
            return
        item = todo_store.new_item(node["text"], self.page_id)
        item["parent_id"] = parent_id
        item["done"] = bool(node.get("done"))
        item["tag"] = node.get("tag")
        item["collapsed"] = bool(node.get("collapsed"))
        item["fired"] = node.get("fired")
        if node.get("snooze"):
            item["snooze_until"] = node["snooze"].strftime(todo_store.DATETIME_FMT)
        self.items.append(item)
        if node.get("archive"):
            self.archive_ids.append(item["id"])
        for child in node.get("children", ()):
            self.add(child, item["id"])


def _build_profile(name: str, pages, make_task, now: datetime, cfg: dict) -> None:
    """name 프로필 DB 를 만들고 예제 페이지 / Task 를 넣는다. 처음 열 페이지는 첫 예제 페이지.
    사용자 태그 같은 설정은 cfg 에 고쳐 넣는다 (저장은 부르는 쪽). 다 넣으면 DB 를 닫는다."""
    profiles.create(name)
    db.connect(profiles.path(name))
    try:
        items, archive_ids, trash, first = [], [], [], None
        for page_name, build in pages:
            page = todo_pages.load()[0] if page_name is None else todo_pages.add(page_name)
            if page is None:
                raise RuntimeError(f"예제 페이지를 만들지 못했습니다: {page_name}")
            builder = _Builder(page["id"], now, cfg)
            for node in build(builder):
                builder.add(node)
            items += builder.items
            archive_ids += builder.archive_ids
            trash += builder.trash
            first = page["id"] if first is None else first
        todo_store.save_todos(items)
        todo_store.archive_items(archive_ids)
        todo_trash.record(trash)
        task_store.register(*make_task(now))
        todo_pages.set_last_page(first)
    finally:
        db.close()


class DataInUse(Exception):
    """데이터 폴더의 파일을 다른 프로그램(켜 둔 디버그 앱, DB 브라우저 등)이 열고 있어 지우지 않았다"""


def _clear(base: str) -> None:
    """데이터 폴더를 통째로 지운다. 먼저 이름을 바꿔 보고, 열린 파일이 있어 바꾸지 못하면 아무것도 지우지 않고
    DataInUse - 반쯤 지운 데이터가 남지 않게 (Windows 는 열린 파일이 든 폴더의 이름을 바꾸지 못한다).
    지난번에 다 지우지 못하고 남은 폴더(<base>.old-...)도 함께 치운다."""
    for left in glob.glob(glob.escape(base) + ".old-*"):
        shutil.rmtree(left, ignore_errors=True)
    if not os.path.exists(base):
        return
    trash = f"{base}.old-{datetime.now():%Y%m%d-%H%M%S-%f}"
    try:
        os.rename(base, trash)
    except OSError as e:
        raise DataInUse(str(e)) from e
    shutil.rmtree(trash, ignore_errors=True)


def fresh(now: datetime | None = None) -> list:
    """데이터 폴더를 비우고 설정(실제 앱 설정 바탕) / 프로필을 예제로 새로 만든다. 만든 프로필 이름 목록.
    .debug_appdata 가 아니면 아무것도 하지 않는다(빈 목록). 쓰는 파일이 있으면 DataInUse (그대로 둠).
    DB 는 닫아 둔다 - 앱이 평소처럼 시작 프로필(cfg profile)을 연다."""
    if not is_debug_data():
        return []
    now = now or datetime.now()
    old = widget_config.load_config()
    _clear(os_win.user_data_dir())

    cfg, _ = _base_config()  # 지운 뒤에 - 실제 설정이 없으면 기본값
    cfg.update(DEBUG_CONFIG)
    cfg.update({key: old.get(key) for key in KEEP_CONFIG_KEYS})
    exports = paths.data_path(EXPORT_FOLDER)
    os.makedirs(exports, exist_ok=True)
    cfg["export_dir"] = exports
    _apply_overrides(cfg, _user_overrides() or {})  # 사용자가 적은 디버그 설정이 가장 나중 (이긴다)
    for name, pages, make_task in PROFILES:
        _build_profile(name, pages, make_task, now, cfg)
    widget_config.save_config(cfg)  # 예제가 넣은 사용자 태그까지
    return [name for name, _, _ in PROFILES]


def prepare(keep: bool | None = None, now: datetime | None = None) -> str:
    """디버그 앱 시작: 데이터를 처음 상태로 새로 만든다(fresh). keep(기본: 환경변수 KEEP_ENV 가 "1")이면
    있던 데이터로 이어서 한다 - 프로필이 하나도 없으면(처음) 만든다.
    앱 로그에 찍을 한 줄을 돌려준다 (이모지 없음 - cp949 콘솔에서 깨짐)."""
    if not is_debug_data():
        return f"데이터 폴더가 {DEBUG_DIR} 가 아니라 디버그 데이터를 만들지 않습니다"
    if keep is None:
        keep = os.environ.get(KEEP_ENV) == "1"
    if keep and profiles.names():
        return "지난 디버그 데이터로 이어서 실행합니다"
    try:
        made = fresh(now)
    except DataInUse as e:
        return f"데이터 폴더를 쓰는 프로그램이 있어 지난 데이터로 이어서 실행합니다 ({e})"
    source = "실제 앱 설정" if widget_config.read_import(real_config_path()) else "기본 설정"
    overrides = _user_overrides()
    if overrides is None:
        source += f" ({USER_CONFIG} 를 읽지 못해 쓰지 않음)"
    elif overrides:
        source += f" + {USER_CONFIG}"
    return (
        f"디버그 데이터를 처음 상태로 새로 만들었습니다"
        f" (설정: {source}, 프로필 {len(made)}개, 예제 페이지 {len(PAGES)}개)"
    )


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    # 이 도구는 디버그 데이터만 만든다 - 실제 %APPDATA%\TaskPin 을 건드리지 않게 APPDATA 를 직접 정한다
    os.environ["APPDATA"] = os.path.join(ROOT, DEBUG_DIR)
    try:
        made = fresh()
    except DataInUse as e:
        print(f"켜 둔 디버그 앱(또는 DB 를 연 프로그램)을 끄고 다시 실행하세요: {e}")
        sys.exit(1)
    print(f"{os_win.user_data_dir()} 를 새로 만들었습니다 - 프로필: {', '.join(made)}")

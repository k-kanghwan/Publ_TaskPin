"""디버그 실행용 예제 데이터: 기능마다 "🧪 ..." TODO 페이지를 만든다 (Qt 없음)

TASKPIN_DEBUG=1 실행(TaskPinApp)이 시작할 때 ensure() 를 부른다. 데이터 폴더가 .debug_appdata 일 때만
만들고, 이미 있는 예제 페이지는 건드리지 않는다 - 체크하던 상태가 저장 시 재시작(dev_run)에도 남는다.
예제 페이지를 지우면(또는 "모든 데이터 초기화") 다음 디버그 실행 때 새로 만든다.

    python tools/debug_seed.py          # 없는 예제 페이지만 만들기
    python tools/debug_seed.py --reset  # 예제 페이지를 지우고 다시 만들기 (리마인더 시각도 지금 기준으로)

명령줄 실행도 APPDATA 를 .debug_appdata 로 바꿔야 한다(아니면 아무것도 하지 않음). 디버그 앱은 꺼 두고 실행한다 -
켜진 앱은 메모리의 목록으로 저장하면서 새로 넣은 할 일을 지운다.

페이지마다 맨 위에 "✅ 확인할 것"(빨간 태그) 체크리스트를 두고, 구분선 아래에 시험할 예제 데이터를 둔다.
빌드에는 들어가지 않는다 - TaskPin.py 는 importlib 로 불러 Nuitka 가 따라가지 않는다.
"""

import os
import sys
from datetime import datetime, timedelta

if __name__ == "__main__":  # python tools/debug_seed.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager import (
    db,
    os_win,
    todo_pages,
    todo_store,
    todo_trash,
    widget_config,
)

DEBUG_DIR = ".debug_appdata"
PREFIX = "🧪 "
CHECK_TITLE = "✅ 확인할 것"
CUSTOM_TAG = ("🧪검토", "#8e7cc3")  # 예제용 사용자 태그 (이름, 색)
DELETED_TAG = "custom-deleted0"  # 설정에 없는 사용자 태그 - 태그 없음으로 보여야 함


def is_debug_data() -> bool:
    """데이터 폴더가 .debug_appdata 안인지 (실제 %APPDATA%\\TaskPin 에는 절대 넣지 않는다)"""
    parts = os.path.normcase(os_win.user_data_dir()).replace("\\", "/").split("/")
    return os.path.normcase(DEBUG_DIR) in parts


# ==================================================
# 페이지 내용
# ==================================================
# 노드: "글자" 또는 {"text", "done", "tag", "collapsed", "children", "fired", "snooze", "archive"}
def _token(dt: datetime) -> str:
    return todo_store.format_token(dt)


def _task_page(ctx):
    return [
        _check(
            "[등록](E) 창에서 업무명을 비우면 확인 버튼이 꺼지고, Enter 를 누르면 경고 테두리",
            "업무명에 :rocket: 입력 → 🚀 로 바뀌고 Ctrl+Z 로 되돌아감",
            "시작 기본값 = 지금을 15분 단위로 올린 값 (06:36 → 06:45)",
            "상세 업무 여러 줄 + Ctrl+Enter 확인 → 좌하단에 상세, 넘치면 … + 툴팁",
            "가로 모드에서 위젯을 키우면 상세 업무가 더 많은 줄로 보임 (세로는 3줄)",
            "등록 창을 확인 없이 닫고 다시 [등록] → 업무명·상세가 남아 있음",
            "등록 창이 떠 있는 동안 위젯 클릭 → 등록 창이 앞으로, 위젯은 끌어 옮기기만",
            "위젯을 끌어 옮기면 열린 등록 창이 따라옴",
            "[수정](R) → 'Task 수정' 제목, 종료를 미래로 바꾸면 종료 알림을 다시 받음",
            "소요를 짧게 등록 → 0 을 지나면 남은시간 +초과, 트레이 알림 1번",
            "[해제] 확인 버튼이 경고색 / [완료](C) 확인 창에 남은시간 표시",
            "사용자 이름 더블클릭 편집 (좌패널에서 편집되는 곳은 여기뿐)",
            "우클릭 '항상 위에 보이기' 켬 → 다른 앱을 눌러도 위젯이 위에 남음 (깜빡임 없음)",
            "'항상 위에 보이기' 끔 → 다른 앱을 누르면 바탕화면 층으로 내려감",
            "우클릭 가로/세로 모드, 위치/크기 잠금(핸들 꺼짐), 위젯 숨기기 → 트레이로 다시 보이기",
            "하단 핸들 = 높이, 우측 핸들 = 폭 (모드마다 따로 저장)",
            "앱을 한 번 더 실행 → 경고 없이 기존 위젯이 앞으로",
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
            "'완료된 상위' 하위 하나를 해제 → 상위도 해제 / 상위 체크 → 하위 모두 완료",
            "상위 삭제 → 하위가 한 단계 올라감",
            "클릭 / Ctrl+클릭 / Shift+클릭 선택, Space 로 모두 완료·해제",
            "G, G / Shift+G / Home / End 로 맨 위·맨 아래",
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
            "실행하고 약 2분 뒤 '곧 알림' 팝업 → 나중에 알림 / 완료 버튼",
            "Ctrl+F → [전체][오늘][지연][예정] 칩 개수와 거른 목록",
            "검색 '사과 주스' → 두 단어가 모두 든 항목만, 맞는 글자 노란 배경이 2초 뒤 사라짐",
            "검색 'apple' → 대소문자 없이 'Apple' 도 맞음, 상위는 흐리게 함께 보임",
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
        f"곧 알림 (2분 뒤) {_token(now + timedelta(minutes=2))}",
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
            "Del / ✕ → 확인 창 '다시 묻지 않음' (설정 Application 에서 다시 켬)",
            "우클릭 '삭제 이력' → '지운 예제' 묶음 되돌리기 (상위·자리 복원)",
            "우클릭 '완료 항목 정리' → 완료 항목이 보관으로",
            "우클릭 내보내기 → 화면 목록 / 보관 항목 전체 (.md, 페이지 이름이 제목·파일명에)",
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
            "칩을 끌어 순서 바꾸기 (Esc 로 취소), 칩 더블클릭으로 이름 바꾸기",
            "칩 뒤 숫자 = 체크 안 한 할 일 수 (하위 포함, 구분선 제외)",
            "우클릭 새 페이지 / 앞·뒤로 옮기기 / 삭제 (남은 할 일은 삭제 이력으로)",
            "설정 페이지 표시 위치: 위 / 아래 / 왼쪽 / 오른쪽 (왼쪽·오른쪽은 점만)",
            "설정창(Ctrl+,)을 닫았다 열면 마지막 탭부터",
            "추천 테마 드롭다운, 강조색·배경색, 투명도 슬라이더 + '글자도 함께 투명'",
            "드롭다운·슬라이더 위에서 휠 → 값이 바뀌지 않고 페이지만 스크롤",
            "폰트, 좌·우패널 글자 배율",
            "단축키 바꾸기: 두 키(G, G), 겹침 검사, ↶ 되돌리기",
            "Snippets 탭에서 :트리거: 추가 → 할 일 입력에서 바뀜",
            "Application: 앱 아이콘 다크/라이트, 되돌릴 수 있는 삭제 수",
            "설정 내보내기 → 값 바꾸기 → 가져오기 → 원래대로",
            "모든 데이터 초기화 (문구 입력해야 확인 켜짐) → 다음 디버그 실행 때 예제를 다시 만듦",
        ),
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
        ),
        "---",
        *nodes,
    ]


# (페이지 이름, 내용) - 이 순서로 페이지를 만든다
PAGES = (
    (f"{PREFIX}Task·위젯", _task_page),
    (f"{PREFIX}계층·접기", _tree_page),
    (f"{PREFIX}태그·표시", _display_page),
    (f"{PREFIX}리마인더·검색", _reminder_page),
    (f"{PREFIX}편집·이력", _edit_page),
    (f"{PREFIX}페이지·설정", _page_settings_page),
    (f"{PREFIX}대량 150", _bulk_page),
)


def _check(*steps) -> dict:
    return {"text": CHECK_TITLE, "tag": "red", "children": list(steps)}


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


def ensure(now: datetime | None = None, check_dir: bool = True) -> list:
    """없는 예제 페이지를 만들고 만든 페이지 이름 목록을 돌려준다.
    처음 만들 때는 디버그 위젯을 항상 위로 두고, 새로 만든 첫 예제 페이지를 연다(cfg todo_page)."""
    if check_dir and not is_debug_data():
        return []
    now = now or datetime.now()
    have = {page["name"] for page in todo_pages.load()}
    missing = [(name, build) for name, build in PAGES if name not in have]
    if not missing:
        return []

    cfg = widget_config.load_config()
    first_seed = not (have & {name for name, _ in PAGES})
    items = todo_store.load_todos()
    created, archive_ids, trash = [], [], []
    for name, build in missing:
        page = todo_pages.add(name)
        if page is None:
            continue
        builder = _Builder(page["id"], now, cfg)
        for node in build(builder):
            builder.add(node)
        items.extend(builder.items)
        archive_ids += builder.archive_ids
        trash += builder.trash
        created.append(page)

    todo_store.save_todos(items)
    todo_store.archive_items(archive_ids)
    todo_trash.record(trash)
    if created:
        if first_seed:
            cfg["always_on_top"] = True  # 디버그는 위에 띄워 두고 시작 (메뉴로 끌 수 있음)
        cfg["todo_page"] = created[0]["id"]
        widget_config.save_config(cfg)
    return [page["name"] for page in created]


def reset(now: datetime | None = None, check_dir: bool = True) -> list:
    """예제 페이지와 그 할 일(보관 포함)을 지우고 다시 만든다."""
    if check_dir and not is_debug_data():
        return []
    names = {name for name, _ in PAGES}
    page_ids = [page["id"] for page in todo_pages.load() if page["name"] in names]
    c = db.conn()
    with c:
        c.executemany("DELETE FROM todos WHERE page_id = ?", [(i,) for i in page_ids])
    for page_id in page_ids:
        todo_pages.remove(page_id)
    return ensure(now, check_dir)


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if not is_debug_data():
        print(f"APPDATA 가 {DEBUG_DIR} 가 아니라서 하지 않습니다: {os_win.user_data_dir()}")
        sys.exit(1)
    made = reset() if "--reset" in sys.argv[1:] else ensure()
    print("만든 예제 페이지:", ", ".join(made) if made else "없음 (이미 모두 있음)")

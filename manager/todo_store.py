"""위젯 TODO 리스트 영속화(SQLite todos 테이블) + 리마인더 토큰 파싱

obsidian-reminder 와 같이 텍스트 안의 `(@YYYY-MM-DD HH:mm)` 토큰을
리마인더의 단일 원본으로 삼는다. (텍스트를 고치면 리마인더도 같이 바뀜)

TodoPanel 은 메모리 목록을 통째로 save_todos() 에 넘긴다. 저장은 화면 목록(활성 행)만
맞추고, "완료 항목 정리"로 보관한(archived_at) 행은 건드리지 않는다.
"""

import html
import re
import sqlite3
import uuid
from datetime import datetime

from manager import db

DEFAULT_REMIND_TIME = (
    "09:00"  # 날짜만 입력했을 때의 알림 시각 (obsidian-reminder 기본값)
)
DATETIME_FMT = "%Y-%m-%d %H:%M"

REMINDER_RE = re.compile(r"\(@(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\)")

_COLUMNS = ("id", "text", "done", "created", "snooze_until", "fired")


# ==================================================
# 저장 (SQLite)
# ==================================================
def load_todos() -> list:
    """보관하지 않은 TODO 목록을 순서대로 읽어온다. 읽지 못하면 빈 목록을 반환한다."""
    try:
        rows = (
            db.conn()
            .execute(
                f"SELECT {', '.join(_COLUMNS)} FROM todos"
                " WHERE archived_at IS NULL ORDER BY position"
            )
            .fetchall()
        )
    except sqlite3.Error as e:
        print(f"TODO 불러오기 실패: {e}")
        return []
    return [_normalize(dict(row)) for row in rows]


def save_todos(items: list) -> None:
    """화면 목록을 저장한다(목록에서 빠진 활성 행은 삭제). 실패해도 앱 동작을 막지 않는다."""
    c = db.conn()
    try:
        with c:
            keep = {item["id"] for item in items}
            active = [
                row[0]
                for row in c.execute("SELECT id FROM todos WHERE archived_at IS NULL")
            ]
            c.executemany(
                "DELETE FROM todos WHERE id = ?",
                [(item_id,) for item_id in active if item_id not in keep],
            )
            c.executemany(
                f"INSERT INTO todos ({', '.join(_COLUMNS)}, position)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " text = excluded.text, done = excluded.done, created = excluded.created,"
                " snooze_until = excluded.snooze_until, fired = excluded.fired,"
                " position = excluded.position",
                [
                    (
                        item["id"],
                        item["text"],
                        int(bool(item["done"])),
                        item.get("created"),
                        item.get("snooze_until"),
                        item.get("fired"),
                        pos,
                    )
                    for pos, item in enumerate(items)
                ],
            )
    except sqlite3.Error as e:
        print(f"TODO 저장 실패: {e}")


def archive_items(ids: list) -> None:
    """ "완료 항목 정리": 행을 지우지 않고 보관 시각을 기록한다."""
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    c = db.conn()
    try:
        with c:
            c.executemany(
                "UPDATE todos SET archived_at = ? WHERE id = ? AND archived_at IS NULL",
                [(stamp, item_id) for item_id in ids],
            )
    except sqlite3.Error as e:
        print(f"TODO 보관 실패: {e}")


def new_item(text: str) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "text": text,
        "done": False,
        "created": datetime.now().astimezone().strftime(DATETIME_FMT),
        "snooze_until": None,  # "나중에 알림" 으로 미룬 시각
        "fired": None,  # 마지막으로 알림을 보낸 due 문자열
    }


def _normalize(item: dict) -> dict:
    """손으로 고친 파일 등 누락된 키를 기본값으로 채운다."""
    base = new_item(str(item.get("text", "")))
    base.update(item)
    base["done"] = bool(base["done"])
    return base


# ==================================================
# 리마인더 토큰
# ==================================================
def parse_reminder(text: str):
    """텍스트의 마지막 `(@...)` 토큰을 datetime 으로. 없거나 잘못되면 None"""
    matches = REMINDER_RE.findall(text or "")
    if not matches:
        return None
    date_str, time_str = matches[-1]
    try:
        return datetime.strptime(
            f"{date_str} {time_str or DEFAULT_REMIND_TIME}", DATETIME_FMT
        ).astimezone()
    except ValueError:
        return None


def format_token(dt: datetime) -> str:
    return f"(@{dt.strftime(DATETIME_FMT)})"


def strip_reminder(text: str) -> str:
    """표시용: 토큰을 뺀 본문"""
    return " ".join(REMINDER_RE.sub("", text or "").split())


def due_at(item: dict):
    """알림 시각. 미뤄둔 시각이 있으면 그것이 우선이다."""
    snooze = item.get("snooze_until")
    if snooze:
        try:
            return datetime.strptime(snooze, DATETIME_FMT).astimezone()
        except ValueError:
            pass
    return parse_reminder(item.get("text", ""))


def due_key(due: datetime) -> str:
    return due.strftime(DATETIME_FMT)


def is_due(item: dict, now: datetime) -> bool:
    """아직 알리지 않은, 시각이 지난 미완료 리마인더인지"""
    if item.get("done"):
        return False
    due = due_at(item)
    return due is not None and due <= now and item.get("fired") != due_key(due)


def to_html(text: str) -> str:
    """표시용 HTML (반드시 escape - 사용자 입력이 RichText 로 해석되지 않도록)"""
    return html.escape(strip_reminder(text))


if __name__ == "__main__":
    print(parse_reminder("회의자료 준비하기 (@2026-10-21 09:00)"))
    print(parse_reminder("날짜만 (@2026-10-21)"))
    print(strip_reminder("회의자료 (@2026-10-21 09:00) 준비"))

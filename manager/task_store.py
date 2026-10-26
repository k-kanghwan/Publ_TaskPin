"""Task 등록 기록 (SQLite tasks 테이블)

등록할 때마다 새 행을 추가해 기록을 남기고, 위젯에는 가장 최근 행 하나만 표시한다.
"Task 완료"는 행을 지우지 않고 cleared_at 을 기록한다. 가장 최근 행이 완료됐으면 표시할 Task 가 없다.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from manager import db

DATETIME_FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    start_at: datetime
    end_at: datetime
    detail: str = ""  # 상세업무 (여러 줄)


def register(title: str, detail: str, start_at: datetime, end_at: datetime):
    """새 Task 를 기록하고 돌려준다. 저장에 실패하면 None"""
    c = db.conn()
    try:
        with c:
            cur = c.execute(
                "INSERT INTO tasks (title, detail, start_at, end_at, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    title,
                    detail,
                    start_at.strftime(DATETIME_FMT),
                    end_at.strftime(DATETIME_FMT),
                    datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
    except sqlite3.Error as e:
        print(f"Task 저장 실패: {e}")
        return None
    return Task(cur.lastrowid, title, start_at, end_at, detail)


def clear(task_id: int) -> bool:
    """ "Task 완료": 완료 시각을 기록한다. 성공 여부를 반환한다."""
    c = db.conn()
    try:
        with c:
            c.execute(
                "UPDATE tasks SET cleared_at = ? WHERE id = ?",
                (datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), task_id),
            )
    except sqlite3.Error as e:
        print(f"Task 완료 실패: {e}")
        return False
    return True


def latest():
    """가장 최근에 등록한 Task. 없거나, 완료됐거나, 읽지 못하면 None"""
    try:
        row = (
            db.conn()
            .execute(
                "SELECT id, title, detail, start_at, end_at, cleared_at FROM tasks"
                " ORDER BY id DESC LIMIT 1"
            )
            .fetchone()
        )
    except sqlite3.Error as e:
        print(f"Task 불러오기 실패: {e}")
        return None
    if row is None or row["cleared_at"]:
        return None
    try:
        return Task(
            row["id"],
            row["title"],
            datetime.strptime(row["start_at"], DATETIME_FMT).astimezone(),
            datetime.strptime(row["end_at"], DATETIME_FMT).astimezone(),
            row["detail"],
        )
    except ValueError:
        return None


def is_current(task, now: datetime) -> bool:
    """위젯에 표시할 Task 인지.
    시작 날짜가 오늘이 아니고 종료도 지났으면 지난 Task 로 본다.
    (전날 끝난 Task 가 다음 날까지 계속 표시되는 것을 막는다 / 자정을 넘겨 진행 중이면 표시)"""
    if task is None:
        return False
    return task.start_at.date() == now.date() or task.end_at > now


def current_task(now: datetime):
    task = latest()
    return task if is_current(task, now) else None

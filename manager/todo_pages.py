"""TODO 페이지 (SQLite todo_pages 테이블, Qt 없음)

엑셀 시트처럼 페이지마다 독립된 할 일 목록을 둔다. 할 일은 todos.page_id 로 페이지에 속한다.
페이지는 적어도 한 장 있다 (load 가 없으면 만든다 / 마지막 한 장은 지우지 않는다 - TodoPanel).
순서는 position, 이름은 사용자가 바꾼다 (새 페이지는 "페이지 N").
"""

import re
import sqlite3

from manager import db

NAME_PREFIX = "페이지"
NAME_MAX = 20
_NUMBERED_RE = re.compile(rf"{NAME_PREFIX} (\d+)")


def load() -> list:
    """페이지 목록 [{"id", "name"}] (순서대로). 하나도 없으면 첫 페이지를 만든다."""
    c = db.conn()
    try:
        rows = c.execute(
            "SELECT id, name FROM todo_pages ORDER BY position, id"
        ).fetchall()
        if not rows:
            add(f"{NAME_PREFIX} 1")
            rows = c.execute(
                "SELECT id, name FROM todo_pages ORDER BY position, id"
            ).fetchall()
    except sqlite3.Error as e:
        print(f"TODO 페이지 불러오기 실패: {e}")
        return [{"id": 1, "name": f"{NAME_PREFIX} 1"}]
    return [{"id": row["id"], "name": row["name"]} for row in rows]


def clean_name(name: str, fallback: str) -> str:
    """앞뒤 공백을 빼고 NAME_MAX 자로 자른다. 비면 fallback"""
    name = " ".join(name.split())[:NAME_MAX]
    return name or fallback


def next_name(pages: list) -> str:
    """새 페이지 이름: "페이지 N" (지금 있는 "페이지 숫자" 중 가장 큰 수 + 1)"""
    numbers = [
        int(match.group(1))
        for match in (_NUMBERED_RE.fullmatch(page["name"]) for page in pages)
        if match
    ]
    return f"{NAME_PREFIX} {max(numbers, default=0) + 1}"


def add(name: str):
    """맨 뒤에 페이지를 만들고 {"id", "name"} 을 돌려준다. 실패하면 None"""
    c = db.conn()
    try:
        with c:
            position = c.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM todo_pages"
            ).fetchone()[0]
            cursor = c.execute(
                "INSERT INTO todo_pages (name, position) VALUES (?, ?)",
                (name, position),
            )
    except sqlite3.Error as e:
        print(f"TODO 페이지 추가 실패: {e}")
        return None
    return {"id": cursor.lastrowid, "name": name}


def rename(page_id: int, name: str) -> None:
    c = db.conn()
    try:
        with c:
            c.execute("UPDATE todo_pages SET name = ? WHERE id = ?", (name, page_id))
    except sqlite3.Error as e:
        print(f"TODO 페이지 이름 변경 실패: {e}")


def reorder(ids: list) -> None:
    """ids 순서대로 position 을 다시 매긴다."""
    c = db.conn()
    try:
        with c:
            c.executemany(
                "UPDATE todo_pages SET position = ? WHERE id = ?",
                [(position, page_id) for position, page_id in enumerate(ids)],
            )
    except sqlite3.Error as e:
        print(f"TODO 페이지 순서 저장 실패: {e}")


def remove(page_id: int) -> None:
    """페이지만 지운다. 그 페이지의 할 일은 부르는 쪽(TodoPanel)이 먼저 삭제 이력으로 옮긴다.
    (보관한 할 일은 page_id 를 그대로 둔다 - 보관 항목 내보내기는 페이지를 보지 않는다)"""
    c = db.conn()
    try:
        with c:
            c.execute("DELETE FROM todo_pages WHERE id = ?", (page_id,))
    except sqlite3.Error as e:
        print(f"TODO 페이지 삭제 실패: {e}")

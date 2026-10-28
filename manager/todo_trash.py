"""지운 TODO 이력 (SQLite todo_deletions 테이블, Qt 없음)

우패널에서 지운 할 일은 되돌릴 수 있도록 지울 때의 항목 전체와 자리(상위 / 뒤 형제 / 올라간 하위)를
남긴다. 한 번에 지운 항목들(여러 개 선택 삭제, 페이지 삭제)은 같은 batch 로 묶여 함께 되돌아간다.
되돌릴 수 있는 것은 최근 n번의 삭제뿐이고(설정창 Application, widget_config.undo_limit),
이력 행은 되돌려도 지우지 않는다(restored_at 만 기록).
자리 계산 / 되돌리기는 manager/todo_tree 의 removal / restore 가 한다.
"""

import json
import sqlite3
from datetime import datetime

from manager import db

STAMP_FMT = "%Y-%m-%d %H:%M:%S"


def record(entries: list):
    """한 번의 삭제를 한 묶음으로 남긴다.

    Parameters
    ----------
    entries : 지운 순서대로 [{"item": 지울 때의 dict, "parent_id", "before_id", "child_ids"}]

    Returns
    -------
    batch 번호 / 남기지 못했으면 None (삭제 자체는 막지 않는다)
    """
    if not entries:
        return None
    stamp = datetime.now().astimezone().strftime(STAMP_FMT)
    c = db.conn()
    try:
        with c:
            batch = c.execute(
                "SELECT COALESCE(MAX(batch), 0) + 1 FROM todo_deletions"
            ).fetchone()[0]
            c.executemany(
                "INSERT INTO todo_deletions (batch, deleted_at, todo_id, text,"
                " snapshot, parent_id, before_id, child_ids)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        batch,
                        stamp,
                        entry["item"]["id"],
                        entry["item"]["text"],
                        json.dumps(entry["item"], ensure_ascii=False),
                        entry["parent_id"],
                        entry["before_id"],
                        json.dumps(entry["child_ids"]),
                    )
                    for entry in entries
                ],
            )
    except sqlite3.Error as e:
        print(f"삭제 이력 저장 실패: {e}")
        return None
    return batch


def recent(limit: int) -> list:
    """최근 limit 번의 삭제 중 아직 되돌리지 않은 묶음 (최신 순)

    Returns
    -------
    [{"batch", "deleted_at", "entries": [{"item", "parent_id", "before_id", "child_ids"}]}]
    entries 는 지운 순서대로 (되돌릴 때는 거꾸로)
    """
    c = db.conn()
    try:
        batches = [
            row[0]
            for row in c.execute(
                "SELECT DISTINCT batch FROM todo_deletions ORDER BY batch DESC LIMIT ?",
                (limit,),
            )
        ]
        result = []
        for batch in batches:
            rows = c.execute(
                "SELECT deleted_at, snapshot, parent_id, before_id, child_ids,"
                " restored_at FROM todo_deletions WHERE batch = ? ORDER BY id",
                (batch,),
            ).fetchall()
            if any(row["restored_at"] for row in rows):
                continue
            entries = [entry for entry in map(_entry, rows) if entry is not None]
            if entries:
                result.append(
                    {
                        "batch": batch,
                        "deleted_at": rows[0]["deleted_at"],
                        "entries": entries,
                    }
                )
        return result
    except sqlite3.Error as e:
        print(f"삭제 이력 불러오기 실패: {e}")
        return []


def _entry(row):
    """이력 행 하나 -> {"item", "parent_id", "before_id", "child_ids"} / 깨졌으면 None"""
    try:
        item = json.loads(row["snapshot"])
        child_ids = json.loads(row["child_ids"])
    except (TypeError, ValueError):
        return None
    if not (isinstance(item, dict) and "id" in item and isinstance(child_ids, list)):
        return None
    return {
        "item": item,
        "parent_id": row["parent_id"],
        "before_id": row["before_id"],
        "child_ids": child_ids,
    }


def mark_restored(batch: int) -> None:
    """되돌린 묶음에 시각을 남긴다 (이력 행은 지우지 않는다)."""
    stamp = datetime.now().astimezone().strftime(STAMP_FMT)
    c = db.conn()
    try:
        with c:
            c.execute(
                "UPDATE todo_deletions SET restored_at = ?"
                " WHERE batch = ? AND restored_at IS NULL",
                (stamp, batch),
            )
    except sqlite3.Error as e:
        print(f"삭제 이력 갱신 실패: {e}")

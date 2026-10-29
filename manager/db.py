"""SQLite 연결 (%APPDATA%\\TaskPin\\taskpin.db)

연결은 하나만 열어 앱이 끝날 때까지 쓴다. 모든 작업은 UI 스레드에서만 한다.
스키마 버전은 PRAGMA user_version 으로 관리한다.
"모든 데이터 초기화"(설정창 Application)는 지우기 전에 같은 폴더에 백업 파일을 남긴다 (reset_all).
"""

import sqlite3
from datetime import datetime

from manager import paths

DB_NAME = "taskpin.db"
BACKUP_PREFIX = "taskpin-backup"  # 초기화 전 백업: taskpin-backup-YYYYMMDD-HHMMSS.db
# 초기화로 비우는 테이블 (스키마 / user_version 은 그대로)
DATA_TABLES = ("todos", "tasks", "todo_deletions", "todo_pages")
# 초기화 뒤 남기는 첫 페이지 (스키마 v9 가 만드는 것과 같다)
FIRST_PAGE_SQL = "INSERT INTO todo_pages (id, name, position) VALUES (1, '페이지 1', 0)"

# user_version 0 -> 1
_SCHEMA_V1 = """
CREATE TABLE todos (
    id           TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    done         INTEGER NOT NULL DEFAULT 0,
    created      TEXT,
    snooze_until TEXT,
    fired        TEXT,
    position     INTEGER NOT NULL,
    archived_at  TEXT  -- "완료 항목 정리" 로 보관한 시각 / NULL 이면 목록에 표시
);
CREATE TABLE tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL DEFAULT '',
    start_at   TEXT NOT NULL,
    end_at     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
PRAGMA user_version = 1;
"""

# user_version 1 -> 2: "Task 완료" 시각 (기록은 남기고 위젯에서만 내린다)
_SCHEMA_V2 = """
ALTER TABLE tasks ADD COLUMN cleared_at TEXT;
PRAGMA user_version = 2;
"""

# user_version 2 -> 3: TODO 상위 항목 id (NULL 이면 최상위)
_SCHEMA_V3 = """
ALTER TABLE todos ADD COLUMN parent_id TEXT;
PRAGMA user_version = 3;
"""

# user_version 3 -> 4: TODO 색 태그 (todo_store.TAGS / NULL 이면 없음)
_SCHEMA_V4 = """
ALTER TABLE todos ADD COLUMN tag TEXT;
PRAGMA user_version = 4;
"""

# user_version 4 -> 5: Task 상세업무 (등록 창 오른쪽 칸 / 위젯 업무명 배지 위에 표시)
_SCHEMA_V5 = """
ALTER TABLE tasks ADD COLUMN detail TEXT NOT NULL DEFAULT '';
PRAGMA user_version = 5;
"""

# user_version 5 -> 6: Task 를 내린 방식 ('completed' 완료 / 'released' 해제)
# 이전에 내린 Task 는 모두 "Task 완료" 버튼으로 내린 것이다
_SCHEMA_V6 = """
ALTER TABLE tasks ADD COLUMN cleared_as TEXT;
UPDATE tasks SET cleared_as = 'completed' WHERE cleared_at IS NOT NULL;
PRAGMA user_version = 6;
"""

# user_version 6 -> 7: TODO 하위 항목 접힘 (1 이면 하위를 숨김)
_SCHEMA_V7 = """
ALTER TABLE todos ADD COLUMN collapsed INTEGER NOT NULL DEFAULT 0;
PRAGMA user_version = 7;
"""

# user_version 7 -> 8: 지운 TODO 이력 (우패널 우클릭 "삭제 이력"으로 되돌림 - manager/todo_trash)
# 되돌려도 행은 지우지 않고 restored_at 만 남긴다
_SCHEMA_V8 = """
CREATE TABLE todo_deletions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch       INTEGER NOT NULL,  -- 한 번에 지운 묶음 = 되돌리기 단위
    deleted_at  TEXT NOT NULL,
    todo_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    snapshot    TEXT NOT NULL,     -- 지울 때의 항목 전체 (JSON)
    parent_id   TEXT,              -- 지울 때의 상위
    before_id   TEXT,              -- 지울 때 바로 뒤 형제 (NULL: 형제 맨 뒤)
    child_ids   TEXT NOT NULL,     -- 한 단계 위로 올라간 하위 id (JSON 목록)
    restored_at TEXT               -- 되돌린 시각 / NULL 이면 아직 지운 상태
);
PRAGMA user_version = 8;
"""

# user_version 8 -> 9: TODO 페이지 (엑셀 시트처럼 페이지마다 독립된 목록 - manager/todo_pages)
# 지금까지의 할 일은 모두 첫 페이지로
_SCHEMA_V9 = """
CREATE TABLE todo_pages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    position INTEGER NOT NULL
);
INSERT INTO todo_pages (id, name, position) VALUES (1, '페이지 1', 0);
ALTER TABLE todos ADD COLUMN page_id INTEGER NOT NULL DEFAULT 1;
PRAGMA user_version = 9;
"""

_MIGRATIONS = (
    (1, _SCHEMA_V1),
    (2, _SCHEMA_V2),
    (3, _SCHEMA_V3),
    (4, _SCHEMA_V4),
    (5, _SCHEMA_V5),
    (6, _SCHEMA_V6),
    (7, _SCHEMA_V7),
    (8, _SCHEMA_V8),
    (9, _SCHEMA_V9),
)

_conn = None


def connect(path: str | None = None) -> sqlite3.Connection:
    """DB 를 열고(없으면 스키마 생성) 전역 연결로 둔다. path 는 테스트용"""
    global _conn
    close()
    _conn = sqlite3.connect(path or paths.data_path(DB_NAME))
    _conn.row_factory = sqlite3.Row
    _migrate(_conn)
    return _conn


def conn() -> sqlite3.Connection:
    return _conn if _conn is not None else connect()


def close():
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def backup(path: str) -> None:
    """지금 DB 를 path 에 그대로 복사한다 (sqlite backup - 일관된 사본). 실패하면 sqlite3.Error"""
    target = sqlite3.connect(path)
    try:
        conn().backup(target)
    finally:
        target.close()


def wipe() -> None:
    """모든 데이터를 지우고 첫 페이지("페이지 1")만 남긴다. 번호(AUTOINCREMENT)도 처음부터.
    VACUUM 으로 지운 내용이 파일의 빈 공간에 남지 않게 한다. 실패하면 sqlite3.Error"""
    c = conn()
    with c:
        for table in DATA_TABLES:
            c.execute(f"DELETE FROM {table}")
        c.execute("DELETE FROM sqlite_sequence")
        c.execute(FIRST_PAGE_SQL)
    c.execute("VACUUM")


def backup_path(now: datetime) -> str:
    return paths.data_path(f"{BACKUP_PREFIX}-{now:%Y%m%d-%H%M%S}.db")


def reset_all(now: datetime) -> str:
    """ "모든 데이터 초기화": 데이터 폴더에 백업을 남긴 뒤 비운다. 백업 경로를 돌려준다.
    백업하지 못하면 지우지 않는다 (sqlite3.Error / OSError 를 그대로 던짐)."""
    path = backup_path(now)
    backup(path)
    wipe()
    return path


def _migrate(c: sqlite3.Connection):
    version = c.execute("PRAGMA user_version").fetchone()[0]
    for target, script in _MIGRATIONS:
        if version < target:
            c.executescript("BEGIN;" + script + "COMMIT;")

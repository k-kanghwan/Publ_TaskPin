"""SQLite 연결 (%APPDATA%\\TaskPin\\taskpin.db)

연결은 하나만 열어 앱이 끝날 때까지 쓴다. 모든 작업은 UI 스레드에서만 한다.
스키마 버전은 PRAGMA user_version 으로 관리한다.
"""

import sqlite3

from manager import paths

DB_NAME = "taskpin.db"

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

_MIGRATIONS = (
    (1, _SCHEMA_V1),
    (2, _SCHEMA_V2),
    (3, _SCHEMA_V3),
    (4, _SCHEMA_V4),
    (5, _SCHEMA_V5),
    (6, _SCHEMA_V6),
    (7, _SCHEMA_V7),
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


def _migrate(c: sqlite3.Connection):
    version = c.execute("PRAGMA user_version").fetchone()[0]
    for target, script in _MIGRATIONS:
        if version < target:
            c.executescript("BEGIN;" + script + "COMMIT;")

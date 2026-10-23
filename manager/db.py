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

# user_version 1 -> 2: "Task 해제" 시각 (기록은 남기고 위젯에서만 내린다)
_SCHEMA_V2 = """
ALTER TABLE tasks ADD COLUMN cleared_at TEXT;
PRAGMA user_version = 2;
"""

_MIGRATIONS = ((1, _SCHEMA_V1), (2, _SCHEMA_V2))

_conn = None


def connect(path: str | None) -> sqlite3.Connection:
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

"""프로필 (Obsidian 의 vault 처럼): DB 파일 하나가 프로필 하나 (Qt 없음)

%APPDATA%\\TaskPin\\profiles\\<이름>.db - 파일 이름이 곧 프로필 이름이다 (이름을 바꾸면 파일 이름도 바뀐다).
할 일 · 페이지 · 삭제 이력 · Task 기록은 프로필마다 따로고, 설정(config.json)은 모든 프로필이 함께 쓴다.
config "profile" 에 마지막으로 연 프로필 이름을 두고, 마지막으로 본 TODO 페이지는 각 DB 의 meta 에 둔다
(todo_pages.last_page). 이 폴더에 넣은 .db 파일도 목록에 보인다 (vault 폴더를 여는 것처럼).

v0.1.29 까지의 데이터 파일(데이터 폴더의 taskpin.db)은 처음 한 번 기본 프로필로 옮긴다 (migrate_legacy).
여기서는 목록 / 이름 규칙 / 파일 다루기만 한다. 연결을 바꾸는 일(db.connect)과 화면은 TaskPinApp 이 한다.
"""

import os
from datetime import datetime

from manager import db, os_win, paths

FOLDER = "profiles"
EXT = ".db"
DEFAULT_NAME = "기본"
NEW_NAME_PREFIX = "프로필"  # 새 프로필 이름 기본값 ("프로필 2")
NAME_MAX = 30
LEGACY_DB = "taskpin.db"  # v0.1.29 까지 데이터 폴더에 바로 두던 DB
# sqlite 가 DB 옆에 두는 파일 - 이름을 바꾸거나 옮길 때 함께 옮긴다
_SIDE_SUFFIXES = ("-journal", "-wal", "-shm")


def folder() -> str:
    """프로필 폴더 (없으면 만든다)"""
    path = paths.data_path(FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def path(name: str) -> str:
    return os.path.join(folder(), name + EXT)


def names() -> list:
    """프로필 이름 목록 (폴더의 .db 파일, 이름순 - 대소문자 무시). -journal 같은 sqlite 파일은 뺀다."""
    base = folder()
    try:
        entries = os.listdir(base)
    except OSError:
        return []
    result = []
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        if (
            ext.lower() == EXT
            and stem.strip()
            and os.path.isfile(os.path.join(base, entry))
        ):
            result.append(stem)
    return sorted(result, key=str.casefold)


def find(name: str, existing: list | None = None):
    """같은 이름(대소문자 무시 - Windows 파일 이름처럼)의 프로필 이름. 없으면 None"""
    folded = name.casefold()
    for other in names() if existing is None else existing:
        if other.casefold() == folded:
            return other
    return None


def name_error(name: str, existing: list, current: str | None = None) -> str:
    """프로필 이름으로 쓸 수 없으면 그 까닭, 쓸 수 있거나 비었으면 "" (이름 창이 확인 버튼을 끈다).
    current: 이름을 바꾸는 프로필 - 자기 이름 그대로 / 대소문자만 바꾸기는 된다."""
    name = name.strip()
    if not name:
        return ""
    bad = os_win.bad_filename_chars(name)
    if bad:
        shown = " ".join(c for c in bad if ord(c) >= 32)
        return f"쓸 수 없는 글자: {shown}" if shown else "쓸 수 없는 글자가 있습니다"
    if os_win.is_reserved_filename(name):
        return "Windows가 쓰는 이름이라 쓸 수 없습니다"
    if len(name) > NAME_MAX:
        return f"{NAME_MAX}자까지 쓸 수 있습니다"
    if current is not None and name.casefold() == current.casefold():
        return ""
    if find(name, existing) is not None:
        return "같은 이름의 프로필이 있습니다"
    return ""


def unique_name(existing: list) -> str:
    """새 프로필 이름 기본값: "프로필 2", "프로필 3" … 중 아직 없는 것"""
    n = len(existing) + 1
    while find(f"{NEW_NAME_PREFIX} {n}", existing) is not None:
        n += 1
    return f"{NEW_NAME_PREFIX} {n}"


def neighbor(name: str, existing: list):
    """name 을 지운 뒤 열 프로필: 목록에서 바로 앞 (맨 앞이면 뒤). 남는 프로필이 없으면 None"""
    if name not in existing or len(existing) < 2:
        return None
    idx = existing.index(name)
    return existing[idx - 1] if idx > 0 else existing[1]


def startup_name(saved) -> str:
    """시작할 때 열 프로필: 마지막으로 연 것 -> 기본 -> 첫 프로필.
    하나도 없으면 기본 (db.connect 가 파일을 만든다)"""
    existing = names()
    for candidate in (saved, DEFAULT_NAME):
        if isinstance(candidate, str) and candidate.strip():
            found = find(candidate, existing)
            if found is not None:
                return found
    return existing[0] if existing else DEFAULT_NAME


def migrate_legacy() -> bool:
    """v0.1.29 까지 쓰던 데이터 폴더의 taskpin.db 를 기본 프로필(profiles\\기본.db)로 옮긴다.
    프로필이 하나도 없을 때 한 번만 한다. 옮기지 못하면(다른 프로그램이 파일을 잡고 있는 등) 복사한다.
    옮겼으면 True. 복사도 못 하면 만들던 파일을 지우고 예외를 그대로 던진다."""
    legacy = paths.data_path(LEGACY_DB)
    if not os.path.isfile(legacy) or names():
        return False
    target = path(DEFAULT_NAME)
    try:
        _move(legacy, target)
    except OSError:
        _copy_or_clean(lambda: db.copy_file(legacy, target), target)
    return True


def create(name: str) -> None:
    """빈 프로필("페이지 1"만 있는 DB)을 만든다. 같은 이름이 있으면 FileExistsError"""
    db.init_file(path(name))


def duplicate(name: str) -> None:
    """지금 연 DB 를 name 프로필로 복사한다 (sqlite backup - 열린 채로 일관된 사본).
    같은 이름이 있으면 FileExistsError, 복사하지 못하면 만들던 파일을 지우고 sqlite3.Error"""
    target = path(name)
    if os.path.exists(target):
        raise FileExistsError(target)
    _copy_or_clean(lambda: db.backup(target), target)


def rename(old: str, new: str) -> None:
    """닫혀 있는 프로필의 파일 이름을 바꾼다 (지금 프로필이면 부르는 쪽이 먼저 닫는다).
    대소문자만 바꿀 수도 있다. 다른 프로필과 겹치면 FileExistsError (덮어쓰지 않음)"""
    if old == new:
        return
    if old.casefold() != new.casefold() and os.path.exists(path(new)):
        raise FileExistsError(path(new))
    _move(path(old), path(new))


def remove(name: str, now: datetime) -> str:
    """닫혀 있는 프로필을 지운다: 파일을 데이터 폴더의 백업 이름으로 옮겨 목록에서 뺀다.
    ("모든 데이터 초기화"처럼 백업은 사용자에게 따로 말하지 않는다) 옮긴 경로를 돌려준다."""
    target = db.backup_path(name, now)
    _move(path(name), target)
    return target


def check(name: str) -> None:
    """name 프로필을 열 수 있는지 (이 앱의 DB 인지) - db.check_file"""
    db.check_file(path(name))


def _move(source: str, target: str) -> None:
    # os.rename 은 Windows 에서 target 이 있으면 덮어쓰지 않고 FileExistsError (같은 파일의 대소문자 변경은 됨)
    os.rename(source, target)
    for suffix in _SIDE_SUFFIXES:
        if os.path.exists(source + suffix):
            os.replace(source + suffix, target + suffix)


def _copy_or_clean(copy, target: str) -> None:
    """copy() 가 실패하면 반쯤 만든 target 을 지우고 예외를 그대로 던진다
    (빈 파일이 프로필 목록에 남으면 다음 시작 때 옛 데이터를 옮기지 않는다)"""
    try:
        copy()
    except Exception:
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass
        raise

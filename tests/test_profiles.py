import os
import sqlite3
from datetime import datetime

import pytest

from manager import db, paths, profiles, task_store, todo_pages, todo_store


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """임시 데이터 폴더 (실제 %APPDATA%\\TaskPin 은 건드리지 않음). 끝나면 DB 를 닫는다."""
    monkeypatch.setattr(paths, "data_path", lambda name: str(tmp_path / name))
    yield tmp_path
    db.close()


def _fill(path, text):
    db.connect(path)
    todo_store.save_todos([todo_store.new_item(text)])
    db.close()


def test_names_lists_db_files_only(data_dir):
    folder = profiles.folder()
    assert folder == str(data_dir / "profiles") and profiles.names() == []
    for name in ("업무.db", "b.DB", "a.db", "a.db-journal", "메모.txt"):
        open(os.path.join(folder, name), "w").close()
    os.mkdir(os.path.join(folder, "폴더.db"))
    assert profiles.names() == ["a", "b", "업무"]
    assert profiles.find("업무") == "업무"
    assert profiles.find("A") == "a"  # Windows 파일 이름처럼 대소문자 무시
    assert profiles.find("없음") is None


def test_name_error():
    existing = ["업무", "Home"]
    assert profiles.name_error("", existing) == ""  # 빈 이름은 확인 버튼만 끈다
    assert profiles.name_error("개인 🚀", existing) == ""
    assert profiles.name_error(" 개인 ", existing) == ""  # 앞뒤 공백은 뺀다
    assert profiles.name_error("a/b:c", existing) == "쓸 수 없는 글자: / :"
    assert profiles.name_error("탭\t", existing) == ""  # 끝 공백 문자는 strip 으로 빠짐
    assert profiles.name_error("a\tb", existing) == "쓸 수 없는 글자가 있습니다"
    assert "Windows" in profiles.name_error("con", existing)
    assert "Windows" in profiles.name_error("COM1.old", existing)
    assert profiles.name_error("console", existing) == ""
    assert profiles.name_error("가" * (profiles.NAME_MAX + 1), existing)
    assert profiles.name_error("home", existing) == "같은 이름의 프로필이 있습니다"
    # 이름 바꾸기: 자기 이름 그대로 / 대소문자만 바꾸기는 된다
    assert profiles.name_error("home", existing, current="Home") == ""
    assert profiles.name_error("업무", existing, current="Home")


def test_unique_name_and_neighbor():
    assert profiles.unique_name(["기본"]) == "프로필 2"
    assert profiles.unique_name(["기본", "프로필 2", "프로필 3"]) == "프로필 4"
    assert profiles.unique_name(["프로필 2"]) == "프로필 3"
    names = ["a", "b", "c"]
    assert profiles.neighbor("b", names) == "a"  # 앞
    assert profiles.neighbor("a", names) == "b"  # 맨 앞이면 뒤
    assert profiles.neighbor("a", ["a"]) is None  # 마지막 한 프로필
    assert profiles.neighbor("x", names) is None


def test_startup_name(data_dir):
    assert (
        profiles.startup_name(None) == profiles.DEFAULT_NAME
    )  # 처음: 기본 (connect 가 만든다)
    for name in ("업무", "개인"):
        profiles.create(name)
    assert profiles.startup_name("업무") == "업무"
    assert profiles.startup_name("없는 프로필") == "개인"  # 기본이 없으면 첫 프로필
    profiles.create(profiles.DEFAULT_NAME)
    assert profiles.startup_name("없는 프로필") == profiles.DEFAULT_NAME
    assert profiles.startup_name(123) == profiles.DEFAULT_NAME


def test_migrate_legacy_moves_old_db_once(data_dir):
    legacy = str(data_dir / profiles.LEGACY_DB)
    _fill(legacy, "예전 할 일")
    assert profiles.migrate_legacy() is True
    assert not os.path.exists(legacy)
    assert profiles.names() == [profiles.DEFAULT_NAME]
    db.connect(profiles.path(profiles.DEFAULT_NAME))
    assert [i["text"] for i in todo_store.load_todos()] == ["예전 할 일"]
    db.close()

    # 프로필이 이미 있으면 (예전 버전이 다시 만든 파일이 있어도) 건드리지 않는다
    _fill(legacy, "다시 생긴 파일")
    assert profiles.migrate_legacy() is False
    assert os.path.exists(legacy)


def test_migrate_legacy_copies_when_move_fails(data_dir, monkeypatch):
    legacy = str(data_dir / profiles.LEGACY_DB)
    _fill(legacy, "잡혀 있는 파일")

    def locked(*_):
        raise PermissionError("다른 프로그램이 사용 중")

    monkeypatch.setattr(os, "rename", locked)
    assert profiles.migrate_legacy() is True
    assert os.path.exists(legacy)  # 원본은 그대로 두고 복사
    db.connect(profiles.path(profiles.DEFAULT_NAME))
    assert [i["text"] for i in todo_store.load_todos()] == ["잡혀 있는 파일"]


def test_migrate_legacy_does_nothing_on_fresh_install(data_dir):
    assert profiles.migrate_legacy() is False
    assert profiles.names() == []


def test_create_duplicate_rename_remove(data_dir):
    profiles.create("업무")
    db.connect(profiles.path("업무"))
    assert todo_pages.load() == [{"id": 1, "name": "페이지 1"}]  # 빈 프로필
    with pytest.raises(FileExistsError):
        profiles.create("업무")

    # 다른 이름으로 저장: 열린 DB 를 그대로 복사
    todo_store.save_todos([todo_store.new_item("업무 할 일")])
    start = datetime(2026, 11, 3, 9, 0).astimezone()
    task_store.register("업무 Task", "", start, start)
    profiles.duplicate("업무 사본")
    with pytest.raises(FileExistsError):
        profiles.duplicate("업무 사본")
    db.connect(profiles.path("업무 사본"))
    assert [i["text"] for i in todo_store.load_todos()] == ["업무 할 일"]
    assert task_store.latest().title == "업무 Task"
    db.close()

    # 이름 바꾸기 (닫힌 파일): 겹치면 덮어쓰지 않고, 대소문자만 바꾸기는 된다
    with pytest.raises(FileExistsError):
        profiles.rename("업무 사본", "업무")
    profiles.rename("업무 사본", "work")
    profiles.rename("work", "Work")
    assert profiles.names() == ["Work", "업무"]

    # 지우기: 데이터 폴더의 백업 이름으로 옮겨 목록에서 뺀다
    backup = profiles.remove("Work", datetime(2026, 11, 3, 10, 0, 5))
    assert os.path.basename(backup) == "taskpin-backup-Work-20261103-100005.db"
    assert os.path.dirname(backup) == str(data_dir)
    assert profiles.names() == ["업무"]


def test_check(data_dir):
    profiles.create("좋음")
    profiles.check("좋음")
    with open(profiles.path("가짜"), "w", encoding="utf-8") as f:
        f.write("not a database")
    with pytest.raises(sqlite3.DatabaseError):
        profiles.check("가짜")
    with pytest.raises(FileNotFoundError):
        profiles.check("없음")

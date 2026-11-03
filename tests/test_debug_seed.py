import glob
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

from manager import (
    db,
    os_win,
    profiles,
    task_store,
    todo_pages,
    todo_store,
    todo_trash,
    widget_config,
)
from tools import debug_seed

NOW = datetime(2026, 11, 2, 10, 7)
PROFILES = sorted([debug_seed.SEED_PROFILE, debug_seed.PROFILE_B])
PAGE_NAMES = [name for name, _ in debug_seed.PAGES]


@pytest.fixture
def debug_dir(tmp_path, monkeypatch):
    """임시 .debug_appdata\\TaskPin 을 데이터 폴더로 (실제 데이터 경로는 건드리지 않음)"""
    base = tmp_path / debug_seed.DEBUG_DIR / "TaskPin"
    monkeypatch.setattr(os_win, "user_data_dir", lambda: str(base))
    # 실제 앱 설정 대신 (없는) 임시 파일 - 테스트가 실제 %APPDATA%\TaskPin\config.json 을 읽지 않게
    real = tmp_path / "real" / "TaskPin" / "config.json"
    monkeypatch.setattr(debug_seed, "real_config_path", lambda: str(real))
    monkeypatch.delenv(debug_seed.KEEP_ENV, raising=False)
    yield base
    db.close()


def _open(name):
    db.connect(profiles.path(name))


def _page_items(name):
    page = next(p for p in todo_pages.load() if p["name"] == name)
    return [i for i in todo_store.load_todos() if i["page_id"] == page["id"]]


def test_fresh_builds_profiles_pages_and_config(debug_dir):
    assert debug_seed.fresh(NOW) == [debug_seed.SEED_PROFILE, debug_seed.PROFILE_B]
    assert sorted(profiles.names()) == PROFILES

    _open(debug_seed.SEED_PROFILE)
    assert [p["name"] for p in todo_pages.load()] == ["페이지 1", *PAGE_NAMES]
    for name in PAGE_NAMES:
        items = _page_items(name)
        assert items[0]["text"] == debug_seed.CHECK_TITLE  # 맨 위에 체크리스트
        assert items[0]["tag"] == "red"
        assert any(i["parent_id"] == items[0]["id"] for i in items)
        ids = {i["id"] for i in items}
        assert all(i["parent_id"] is None or i["parent_id"] in ids for i in items)
    assert todo_pages.last_page() == todo_pages.load()[1]["id"]  # 첫 예제 페이지

    # 진행 중인 Task: 15분 단위, 다음 15분 단위 시각에 끝남, 상세 업무가 3줄을 넘음
    task = task_store.latest()
    now = NOW.astimezone()
    assert task.title == debug_seed.SEED_TASK
    assert task.start_at < now < task.end_at <= now + timedelta(minutes=15)
    assert task.start_at.minute % 15 == 0 and task.end_at.minute % 15 == 0
    assert task.detail.count("\n") >= 3

    cfg = widget_config.load_config()  # 실제 설정이 없으면 기본값
    assert cfg["always_on_top"] is widget_config.DEFAULT_CONFIG["always_on_top"]
    assert cfg["profile"] == debug_seed.SEED_PROFILE
    assert any(t["name"] == debug_seed.CUSTOM_TAG[0] for t in widget_config.custom_tags(cfg))
    assert cfg["export_dir"] == str(debug_dir / debug_seed.EXPORT_FOLDER)
    assert os.path.isdir(cfg["export_dir"])
    assert cfg["shortcuts"] == widget_config.DEFAULT_SHORTCUTS  # 나머지는 기본값


def test_settings_start_from_real_config_without_touching_it(debug_dir, tmp_path):
    real = tmp_path / "real" / "TaskPin" / "config.json"
    real.parent.mkdir(parents=True)
    saved = {
        "appearance": {"theme": "light", "accent": "#5f84ea"},
        "shortcuts": {"todo_edit": "F2", "todo_delete": "D, D"},
        "custom_tags": [{"id": "custom-87c79855", "name": "WinOffice", "color": "#e86fa4"}],
        "user_name": "실제 이름",
        "always_on_top": False,
        "orientation": "horizontal",
        "pos": [606, 610],
        "visible": False,
        "profile": "실제 프로필",
        "export_dir": "C:/real/export",
        "todo_page": 3,  # 예전 키 - 가져오지 않음
    }
    real.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    before = real.read_bytes()

    assert "실제 앱 설정" in debug_seed.prepare(keep=False, now=NOW)
    cfg = widget_config.load_config()
    assert cfg["appearance"] == saved["appearance"]
    assert cfg["shortcuts"] == saved["shortcuts"]
    assert cfg["user_name"] == "실제 이름"
    assert cfg["always_on_top"] is False
    assert cfg["orientation"] == "horizontal"
    names = [t["name"] for t in widget_config.custom_tags(cfg)]
    assert names == ["WinOffice", debug_seed.CUSTOM_TAG[0]]  # 예제 태그만 더함
    # 디버그 데이터에 맞춘 값: 디버그 위젯 자리 · 보이기 · 예제 프로필 · 디버그 내보내기 폴더
    assert cfg["pos"] is None
    assert cfg["visible"] is True
    assert cfg["profile"] == debug_seed.SEED_PROFILE
    assert cfg["export_dir"] == str(debug_dir / debug_seed.EXPORT_FOLDER)
    assert "todo_page" not in cfg
    assert real.read_bytes() == before  # 실제 설정은 읽기만


def test_debug_config_file_overrides_only_what_it_lists(debug_dir, tmp_path):
    real = tmp_path / "real" / "TaskPin" / "config.json"
    real.parent.mkdir(parents=True)
    real.write_text(
        json.dumps({"appearance": {"theme": "dark", "accent": "#5f84ea", "todo_scale": 115}}),
        encoding="utf-8",
    )
    user = debug_dir.parent / debug_seed.USER_CONFIG  # .debug_appdata 바로 아래 (지우지 않음)
    user.parent.mkdir(parents=True)
    user.write_text(
        json.dumps(
            {
                "_설명": "메모",
                "appearance": {"accent": "#57b07e", "background": "#15201a"},
                "always_on_top": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert debug_seed.user_config_path() == str(user)

    assert f"+ {debug_seed.USER_CONFIG}" in debug_seed.prepare(keep=False, now=NOW)
    cfg = widget_config.load_config()
    assert cfg["appearance"]["accent"] == "#57b07e"
    assert cfg["appearance"]["background"] == "#15201a"
    assert cfg["appearance"]["todo_scale"] == 115  # 적지 않은 항목은 실제 설정 그대로
    assert cfg["always_on_top"] is True
    assert "_설명" not in cfg
    assert user.exists()  # 새로 만들어도 남는다

    user.write_text("{깨짐", encoding="utf-8")
    assert "읽지 못해" in debug_seed.prepare(keep=False, now=NOW)
    assert widget_config.load_config()["appearance"]["accent"] == "#5f84ea"


def test_without_real_config_uses_defaults(debug_dir):
    assert "기본 설정" in debug_seed.prepare(keep=False, now=NOW)
    cfg = widget_config.load_config()
    assert cfg["appearance"] == widget_config.DEFAULT_APPEARANCE


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 알려진 폴더")
def test_real_data_dir_ignores_appdata_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    real = os_win.real_user_data_dir()
    assert not real.startswith(str(tmp_path))
    assert os.path.basename(real) == os_win.APP_ID


def test_examples_cover_data_features(debug_dir):
    debug_seed.fresh(NOW)
    _open(debug_seed.SEED_PROFILE)
    now = NOW.astimezone()

    reminders = _page_items(f"{debug_seed.PREFIX}리마인더·검색")
    dues = [todo_store.due_at(i) for i in reminders if not i["done"]]
    assert any(d and d < now for d in dues)  # 지연
    assert any(d and d.date() == now.date() and d > now for d in dues)  # 오늘
    assert any(d and d.date() > now.date() for d in dues)  # 예정
    assert not any(todo_store.is_due(i, now) for i in reminders)  # 시작하자마자 팝업 없음

    tree = _page_items(f"{debug_seed.PREFIX}계층·접기")
    assert any(i["collapsed"] for i in tree)
    display = _page_items(f"{debug_seed.PREFIX}태그·표시")
    assert {i["tag"] for i in display} >= set(todo_store.TAGS)
    assert any(todo_store.is_separator(i["text"]) for i in display)

    assert any("보관된" in i["text"] for i in todo_store.load_archived())
    assert [e["item"]["text"] for e in todo_trash.recent(10)[0]["entries"]] == [
        "지운 예제 1",
        "지운 예제 2",
    ]


def test_profile_b_has_its_own_todos_and_task(debug_dir):
    debug_seed.fresh(NOW)
    _open(debug_seed.PROFILE_B)
    assert [p["name"] for p in todo_pages.load()] == ["페이지 1"]
    assert todo_pages.last_page() == todo_pages.load()[0]["id"]
    texts = [i["text"] for i in todo_store.load_todos()]
    assert texts[0] == debug_seed.CHECK_TITLE
    assert any("B 프로필 리마인더" in t for t in texts)
    assert task_store.latest().title == debug_seed.PROFILE_B_TASK


def test_fresh_discards_what_testing_changed(debug_dir):
    debug_seed.fresh(NOW)
    # 시험하며 바꾼 것: 설정 · 위젯 자리 · 새 프로필 · 지운 예제 페이지 / 프로필 · 초기화 백업 · 내보낸 파일
    cfg = widget_config.load_config()
    cfg["appearance"] = {**cfg["appearance"], "theme": "light"}
    cfg["pos"] = [10, 20]
    cfg["profile"] = "내 시험"
    widget_config.save_config(cfg)
    db.init_file(profiles.path("내 시험"))
    os.remove(profiles.path(debug_seed.PROFILE_B))
    _open(debug_seed.SEED_PROFILE)
    todo_pages.remove(todo_pages.load()[-1]["id"])
    db.close()
    (debug_dir / "taskpin-backup-기본-20261102-100000.db").write_bytes(b"")
    (debug_dir / debug_seed.EXPORT_FOLDER / "TaskPin-TODO-전체-20261102.md").write_text(
        "x", encoding="utf-8"
    )
    left = debug_dir.parent / "TaskPin.old-지난번"  # 지난번에 다 지우지 못한 폴더
    left.mkdir()
    (left / "config.json").write_text("{}", encoding="utf-8")

    debug_seed.fresh(NOW)
    assert sorted(profiles.names()) == PROFILES
    assert sorted(os.listdir(debug_dir)) == sorted(
        ["config.json", "profiles", debug_seed.EXPORT_FOLDER]
    )
    assert os.listdir(debug_dir / debug_seed.EXPORT_FOLDER) == []
    assert glob.glob(glob.escape(str(debug_dir)) + ".old-*") == []
    cfg = widget_config.load_config()
    assert cfg["appearance"]["theme"] == widget_config.DEFAULT_APPEARANCE["theme"]
    assert cfg["profile"] == debug_seed.SEED_PROFILE
    assert cfg["pos"] == [10, 20]  # 창 자리만 이어 받는다
    _open(debug_seed.SEED_PROFILE)
    assert [p["name"] for p in todo_pages.load()] == ["페이지 1", *PAGE_NAMES]


@pytest.mark.skipif(sys.platform != "win32", reason="열린 파일이 든 폴더의 이름을 못 바꾸는 것은 Windows 규칙")
def test_data_in_use_is_left_alone(debug_dir):
    debug_seed.fresh(NOW)
    _open(debug_seed.SEED_PROFILE)  # 켜 둔 디버그 앱처럼 DB 를 연 채
    before = sorted(os.listdir(debug_dir))
    with pytest.raises(debug_seed.DataInUse):
        debug_seed.fresh(NOW)
    assert "이어서" in debug_seed.prepare(keep=False, now=NOW)
    assert sorted(os.listdir(debug_dir)) == before
    assert sorted(profiles.names()) == PROFILES
    assert len(todo_pages.load()) == len(PAGE_NAMES) + 1


def test_prepare_keep_continues_or_builds_first_time(debug_dir, monkeypatch):
    monkeypatch.setenv(debug_seed.KEEP_ENV, "1")
    assert "새로" in debug_seed.prepare(now=NOW)  # 처음(프로필 없음)은 만든다
    _open(debug_seed.PROFILE_B)
    todo_pages.add("시험 페이지")
    db.close()

    assert "이어서" in debug_seed.prepare(now=NOW)  # dev_run 저장 시 재시작: 그대로
    _open(debug_seed.PROFILE_B)
    assert "시험 페이지" in [p["name"] for p in todo_pages.load()]
    db.close()

    monkeypatch.delenv(debug_seed.KEEP_ENV)
    assert "새로" in debug_seed.prepare(now=NOW)  # 새 디버그 실행: 처음 상태
    _open(debug_seed.PROFILE_B)
    assert "시험 페이지" not in [p["name"] for p in todo_pages.load()]


def test_refuses_real_data_dir(tmp_path, monkeypatch):
    real = tmp_path / "AppData" / "Roaming" / "TaskPin"
    real.mkdir(parents=True)
    (real / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(os_win, "user_data_dir", lambda: str(real))
    assert not debug_seed.is_debug_data()
    assert debug_seed.fresh(NOW) == []
    assert "만들지 않습니다" in debug_seed.prepare(keep=False, now=NOW)
    assert os.listdir(real) == ["config.json"]

    monkeypatch.setattr(
        os_win, "user_data_dir", lambda: r"C:\repo\.debug_appdata\TaskPin"
    )
    assert debug_seed.is_debug_data()

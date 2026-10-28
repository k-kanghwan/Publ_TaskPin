import json
from datetime import datetime

from manager import widget_config

NOW = datetime(2026, 10, 26, 9, 5, 7)


# ==================================================
# 사용자 태그
# ==================================================
def test_custom_tags_filter_broken_entries():
    cfg = {
        "custom_tags": [
            {"id": "custom-aa", "name": " Home ", "color": "#3FA7A0"},
            {"id": "custom-aa", "name": "중복", "color": "#000000"},
            {"id": "red", "name": "기본 키", "color": "#ff0000"},
            {"id": "custom-bb", "name": "", "color": "#112233"},
            {"id": "custom-cc", "name": "색 없음", "color": "blue"},
            "broken",
        ]
    }
    assert widget_config.custom_tags(cfg) == [
        {"id": "custom-aa", "name": "Home", "color": "#3fa7a0"},
        {"id": "custom-bb", "name": "#112233", "color": "#112233"},  # 이름이 없으면 색
    ]
    assert widget_config.custom_tags({"custom_tags": "x"}) == []
    assert widget_config.custom_tags({}) == []


def test_add_custom_tag_appends_with_new_id():
    cfg = {}
    first = widget_config.add_custom_tag(cfg, "Home", "#3fa7a0")
    second = widget_config.add_custom_tag(cfg, "Work", "#112233")
    assert first != second and first.startswith(widget_config.CUSTOM_TAG_PREFIX)
    assert [t["name"] for t in widget_config.custom_tags(cfg)] == ["Home", "Work"]


# ==================================================
# 설정 내보내기 / 가져오기
# ==================================================
def test_export_writes_config_as_is(tmp_path):
    cfg = {**widget_config.DEFAULT_CONFIG, "user_name": "김유신", "export_dir": "D:\\x"}
    path = widget_config.export_config(cfg, str(tmp_path), NOW)
    assert path == str(tmp_path / "TaskPin-config-20261026.json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == cfg

    # 같은 날 다시 내보내면 덮어쓰지 않고 시각을 붙인다
    second = widget_config.export_config(cfg, str(tmp_path), NOW)
    assert second == str(tmp_path / "TaskPin-config-20261026-090507.json")


def test_import_round_trip(tmp_path):
    cfg = {
        **widget_config.DEFAULT_CONFIG,
        "orientation": "horizontal",
        "shortcuts": {"task_register": "R"},
        "export_dir": "D:\\x",
    }
    path = widget_config.export_config(cfg, str(tmp_path), NOW)
    assert widget_config.read_import(path) == cfg


def test_import_fills_defaults_and_drops_unknown_keys(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"user_name": "a", "unknown": 1}), encoding="utf-8")
    result = widget_config.read_import(str(path))
    assert result == {**widget_config.DEFAULT_CONFIG, "user_name": "a"}
    # 기본값 dict 를 공유하지 않는다
    result["appearance"]["theme"] = "light"
    assert widget_config.DEFAULT_APPEARANCE["theme"] == "dark"


def test_import_rejects_non_config(tmp_path):
    cases = {
        "broken.json": "{not json",
        "list.json": "[1, 2]",
        "other.json": json.dumps({"name": "package"}),
    }
    for name, text in cases.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        assert widget_config.read_import(str(path)) is None, name
    assert widget_config.read_import(str(tmp_path / "missing.json")) is None


# ==================================================
# Appearance
# ==================================================
def test_confirm_delete_and_undo_limit():
    assert widget_config.confirm_delete({}) is True
    assert widget_config.confirm_delete({"confirm_delete": "no"}) is True
    assert widget_config.confirm_delete({"confirm_delete": False}) is False
    assert widget_config.undo_limit({}) == widget_config.DEFAULT_UNDO_LIMIT
    assert widget_config.undo_limit({"undo_limit": 20}) == 20
    assert (
        widget_config.undo_limit({"undo_limit": 7}) == widget_config.DEFAULT_UNDO_LIMIT
    )
    assert widget_config.undo_limit({"undo_limit": True}) == (
        widget_config.DEFAULT_UNDO_LIMIT
    )


def test_appearance_defaults():
    assert widget_config.appearance({}) == widget_config.DEFAULT_APPEARANCE
    assert widget_config.appearance({"appearance": "broken"}) == (
        widget_config.DEFAULT_APPEARANCE
    )


def test_appearance_keeps_valid_values():
    saved = {
        "theme": "light",
        "accent": "#E57373",
        "background": "#202830",
        "font_family": " Noto Sans KR ",
        "left_scale": 115,
        "todo_scale": 130,
        "todo_text_color": "#ffffff",
        "todo_strike": False,
        "todo_row_lines": True,
        "page_bar": "left",
        "fade_text": True,
        "popup_width": 380,
        "popup_scale": 130,
    }
    result = widget_config.appearance({"appearance": saved})
    assert result == {
        **saved,
        "accent": "#e57373",
        "font_family": "Noto Sans KR",
    }


def test_appearance_replaces_broken_values():
    saved = {
        "theme": "blue",
        "accent": "#zzz",
        "background": "red",
        "font_family": 3,
        "left_scale": 130,  # 좌패널은 115 까지
        "todo_scale": 100.0,
        "todo_text_color": "#12345",
        "todo_strike": 0,  # bool 만 받는다
        "todo_row_lines": "on",
        "page_bar": "middle",  # 정해진 위치만
        "fade_text": "yes",  # bool 만 받는다
        "popup_width": 300,  # 정해진 폭만
        "popup_scale": 200,
    }
    result = widget_config.appearance({"appearance": saved})
    assert result == widget_config.DEFAULT_APPEARANCE


def test_appearance_fills_missing_keys():
    result = widget_config.appearance({"appearance": {"theme": "system"}})
    assert result == {**widget_config.DEFAULT_APPEARANCE, "theme": "system"}


def test_appearance_rejects_bool_scale():
    result = widget_config.appearance({"appearance": {"todo_scale": True}})
    assert result["todo_scale"] == 100

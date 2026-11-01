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


def test_app_icon():
    assert widget_config.app_icon({}) == "dark"
    assert widget_config.app_icon({"app_icon": "light"}) == "light"
    for broken in ("blue", 1, None, ["light"]):
        assert widget_config.app_icon({"app_icon": broken}) == "dark"


def test_opacity_and_transparency():
    assert widget_config.opacity({}) == 1.0
    assert widget_config.opacity({"opacity": 0.65}) == 0.65
    assert widget_config.opacity({"opacity": 0.05}) == widget_config.OPACITY_MIN
    for broken in ("0.5", None, True, [1]):
        assert widget_config.opacity({"opacity": broken}) == 1.0
    assert widget_config.transparency({"opacity": 0.65}) == 35

    cfg = {}
    widget_config.set_transparency(cfg, 35)
    assert cfg["opacity"] == 0.65
    widget_config.set_transparency(cfg, 95)  # 최대 투명도까지만
    assert cfg["opacity"] == round(1 - widget_config.TRANSPARENCY_MAX / 100, 2)


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
        "todo_guides": False,
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
        "todo_guides": None,
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


def _preset(preset_id: str) -> dict:
    return next(p for p in widget_config.COLOR_PRESETS if p["id"] == preset_id)


def test_color_presets_are_valid():
    ids = [p["id"] for p in widget_config.COLOR_PRESETS]
    assert len(set(ids)) == len(ids)
    for preset in widget_config.COLOR_PRESETS:
        colors = {key: preset[key] for key in widget_config.PRESET_COLORS}
        # appearance() 가 바로잡지 않는 값이어야 고른 뒤에도 같은 추천 테마로 보인다
        result = widget_config.appearance({"appearance": colors})
        assert {key: result[key] for key in colors} == colors
        if preset["background"]:
            # 다크 / 라이트가 배경 밝기(theme.build 기준)와 맞아야 메뉴 / 설정창이 위젯과 같은 쪽 색이 된다
            rgb = [int(preset["background"][i : i + 2], 16) for i in (1, 3, 5)]
            assert preset["dark"] == ((max(rgb) + min(rgb)) / 2 / 255 < 0.5)
        if "transparency" in preset:
            assert 0 <= preset["transparency"] <= widget_config.TRANSPARENCY_MAX


def test_color_preset_default_on_any_theme():
    default = widget_config.DEFAULT_APPEARANCE
    assert widget_config.color_preset(default, True) == "default"
    assert widget_config.color_preset({**default, "theme": "light"}, True) == "default"
    assert widget_config.color_preset({**default, "accent": "#123456"}, True) is None


def test_with_preset_round_trip_keeps_other_values():
    for system_dark in (True, False):
        for name in widget_config.THEMES:
            values = {
                **widget_config.DEFAULT_APPEARANCE,
                "theme": name,
                "todo_scale": 130,
            }
            for preset in widget_config.COLOR_PRESETS:
                result = widget_config.with_preset(values, preset, system_dark)
                assert result["todo_scale"] == 130  # 색 / 테마 말고는 그대로
                assert widget_config.color_preset(result, system_dark) == preset["id"]


def test_with_preset_changes_theme_only_when_needed():
    dark = {**widget_config.DEFAULT_APPEARANCE, "theme": "dark"}
    light = {**dark, "theme": "light"}
    system = {**dark, "theme": "system"}
    paper, forest = _preset("paper"), _preset("forest")
    assert widget_config.with_preset(dark, paper, True)["theme"] == "light"
    assert widget_config.with_preset(dark, forest, True)["theme"] == "dark"
    assert widget_config.with_preset(light, forest, True)["theme"] == "dark"
    # 시스템 테마는 OS 의 다크 / 라이트가 맞으면 그대로 둔다
    assert widget_config.with_preset(system, forest, True)["theme"] == "system"
    assert widget_config.with_preset(system, forest, False)["theme"] == "dark"
    assert widget_config.with_preset(system, paper, False)["theme"] == "system"
    # 기본은 테마를 바꾸지 않는다
    assert widget_config.with_preset(light, _preset("default"), True)["theme"] == "light"
    # 추천 테마를 고른 뒤 테마만 바꾸면 사용자 지정
    chosen = widget_config.with_preset(dark, forest, True)
    assert widget_config.color_preset({**chosen, "theme": "light"}, True) is None

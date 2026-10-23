from manager import widget_config


# ==================================================
# Appearance
# ==================================================
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
    }
    result = widget_config.appearance({"appearance": saved})
    assert result == widget_config.DEFAULT_APPEARANCE


def test_appearance_fills_missing_keys():
    result = widget_config.appearance({"appearance": {"theme": "system"}})
    assert result == {**widget_config.DEFAULT_APPEARANCE, "theme": "system"}


def test_appearance_rejects_bool_scale():
    result = widget_config.appearance({"appearance": {"todo_scale": True}})
    assert result["todo_scale"] == 100

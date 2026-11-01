from manager import colors, widget_config


def test_contrast_bounds():
    assert round(colors.contrast("#ffffff", "#000000"), 1) == 21.0
    assert colors.contrast("#4a7bd0", "#4a7bd0") == 1.0
    assert colors.contrast("#000000", "#ffffff") == colors.contrast("#ffffff", "#000000")


def test_is_dark():
    assert colors.is_dark("#141414")
    assert not colors.is_dark("#f5f0e6")


def _check_readable(bg: str):
    text = colors.text_colors(bg)
    for field, _on_dark, _on_light, min_contrast in colors.TEXT_LEVELS:
        assert colors.contrast(text[field], bg) >= min_contrast, (bg, field)
    # 본문 > 보조 > 흐린 글자 순으로 배경과 멀다
    assert (
        colors.contrast(text["text_main"], bg)
        > colors.contrast(text["text_sub"], bg)
        > colors.contrast(text["text_dim"], bg)
    )
    # 어두운 배경엔 밝은 글자, 밝은 배경엔 어두운 글자
    assert colors.is_dark(text["text_main"]) != colors.is_dark(bg)


def test_preset_text_is_readable():
    for preset in widget_config.COLOR_PRESETS:
        if preset["background"]:
            _check_readable(preset["background"])


def test_custom_backgrounds_are_readable():
    for bg in ("#000000", "#ffffff", "#141414", "#3a1f5c", "#d8e8ff", "#7a2020"):
        _check_readable(bg)


def test_text_takes_background_tint():
    r, g, b = (int(colors.text_colors("#172033")["text_main"][i : i + 2], 16) for i in (1, 3, 5))
    assert b > r  # 남색 배경 -> 푸른 기가 도는 흰색
    gray = colors.text_colors("#202020")["text_main"]
    assert gray[1:3] == gray[3:5] == gray[5:7]  # 회색 배경 -> 회색 글자


def test_mid_tone_falls_back_to_farthest():
    # 중간 밝기 배경은 7:1 이 안 되므로 가장 먼 색(검정 / 흰색)까지 가고, 보조 글자는 4.5:1 을 지킨다
    assert colors.text_colors("#808080")["text_main"] == "#000000"
    text = colors.text_colors("#5a6a7a")
    assert text["text_main"] == "#ffffff"
    assert colors.contrast(text["text_sub"], "#5a6a7a") >= 4.5

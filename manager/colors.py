"""색 계산 (Qt 없음): 대비율(WCAG)과 배경에 어울리는 글자색

위젯 배경색을 고르면(추천 테마 포함) 글자색은 회색 대신 배경의 색조를 옅게 띤 색으로 바꾸고,
배경 대비 최소 대비율을 지킬 때까지 밝기(어두운 배경) / 어둡기(밝은 배경)를 늘린다 (theme.build).
"""

import colorsys

# (Theme 필드, 어두운 배경일 때 밝기, 밝은 배경일 때 밝기, 배경 대비 최소 대비율)
# 대비율은 WCAG 기준 - 본문 7(AAA) / 보조 4.5(AA). 흐린 글자 / 사용 불가는 기본 테마와 비슷하게
TEXT_LEVELS = (
    ("text_main", 0.90, 0.16, 7.0),
    ("text_sub", 0.68, 0.40, 4.5),
    ("text_disabled", 0.46, 0.62, 2.5),
    ("text_dim", 0.40, 0.66, 2.2),
)
# 중요 항목(본문이 `!` 로 시작)의 무지개 글자: 한 글자마다 색상환을 이만큼 돈다, 배경 대비 최소 대비율
RAINBOW_HUE_STEP = 1 / 12
RAINBOW_SATURATION = 0.8
RAINBOW_CONTRAST = 4.5
RAINBOW_HUES = 120  # 색상을 이 칸으로 끊어 계산해 둔다 (흐르는 색을 그릴 때마다 다시 재지 않게)
_RAINBOW_CACHE = {}
TINT_SATURATION = 0.3  # 글자색 채도 상한 (배경 채도가 더 낮으면 배경 채도 - 회색 배경이면 회색 글자)
_STEP = 0.01


def _rgb(color: str) -> tuple:
    return tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))


def _hex(rgb: tuple) -> str:
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def is_dark(color: str) -> bool:
    """HSL 밝기가 0.5 미만인지 (QColor.lightnessF 와 같은 기준)"""
    return colorsys.rgb_to_hls(*_rgb(color))[1] < 0.5


def luminance(color: str) -> float:
    """WCAG 상대 휘도"""
    channels = [
        v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        for v in _rgb(color)
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a: str, b: str) -> float:
    """WCAG 대비율 (1 ~ 21)"""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def text_color(bg: str, lightness: float, min_contrast: float) -> str:
    """bg 의 색조를 옅게 띤 글자색. bg 대비 min_contrast 가 될 때까지 bg 에서 멀어진다
    (끝까지 가도 안 되면 가장 먼 색 - 중간 밝기 배경)"""
    hue, bg_lightness, saturation = colorsys.rgb_to_hls(*_rgb(bg))
    saturation = min(saturation, TINT_SATURATION)
    step = _STEP if bg_lightness < 0.5 else -_STEP
    while True:
        color = _hex(colorsys.hls_to_rgb(hue, lightness, saturation))
        if contrast(color, bg) >= min_contrast or lightness in (0.0, 1.0):
            return color
        lightness = min(1.0, max(0.0, lightness + step))


def rainbow_color(hue: float, bg: str) -> str:
    """bg 위에서 읽히는(대비 RAINBOW_CONTRAST 이상) 그 색상의 선명한 색"""
    slot = round((hue % 1.0) * RAINBOW_HUES) % RAINBOW_HUES
    key = (slot, bg)
    color = _RAINBOW_CACHE.get(key)
    if color is None:
        dark = is_dark(bg)
        lightness = 0.62 if dark else 0.42
        step = _STEP if dark else -_STEP
        while True:
            rgb = colorsys.hls_to_rgb(slot / RAINBOW_HUES, lightness, RAINBOW_SATURATION)
            color = _hex(rgb)
            if contrast(color, bg) >= RAINBOW_CONTRAST or lightness in (0.0, 1.0):
                break
            lightness = min(1.0, max(0.0, lightness + step))
        _RAINBOW_CACHE[key] = color
    return color


def rainbow(count: int, phase: float, bg: str) -> list:
    """글자 count 개의 무지개 색 (글자마다 RAINBOW_HUE_STEP 씩). phase(0 ~ 1)를 밀면 색이 흐른다"""
    return [rainbow_color(phase + i * RAINBOW_HUE_STEP, bg) for i in range(count)]


def text_colors(bg: str) -> dict:
    """bg 위의 글자색 {Theme 필드: "#rrggbb"} (TEXT_LEVELS)"""
    dark = is_dark(bg)
    return {
        field: text_color(bg, on_dark if dark else on_light, min_contrast)
        for field, on_dark, on_light, min_contrast in TEXT_LEVELS
    }

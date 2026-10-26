"""위젯 공통 테마 (clock_widget / todo_panel / reminder_* / task_picker / confirm_dialog 가 함께 사용)

설정창 Appearance 탭의 값(config.json "appearance")으로 build() 한 Theme 을 set_current() 로 걸어 두고,
각 화면은 스타일을 만들 때 current() 를 읽는다. 위젯은 apply_appearance() 로 다시 입히고,
팝업은 띄울 때마다 새로 만들므로 그때의 테마를 따른다.
설정창은 테마(다크 / 라이트)와 강조색만 따른다 (settings_dialog._settings_theme).
우클릭 메뉴는 배경색을 골라도 테마 설정(다크 / 라이트)을 따른다.
"""

from dataclasses import dataclass, replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

CORNER_RADIUS = 14
FALLBACK_FONTS = "'Malgun Gothic', 'Segoe UI', sans-serif"


@dataclass(frozen=True)
class Theme:
    dark: bool
    # 배경은 불투명 - 위젯 투명도는 위젯의 투명도 슬라이더(setWindowOpacity)로만 정한다
    bg: str  # 위젯 배경 (paintEvent)
    popup_bg: str  # Task 등록 창 / 리마인더 피커 / 리마인더 팝업 배경
    dialog_bg: str  # 확인 창 배경 - 위젯 위에 떠 보이도록 위젯과 조금 다르게
    # 우클릭 메뉴는 배경색과 관계없이 테마(다크 / 라이트) 설정을 따른다 - build() 의 MENU_FIELDS
    menu_bg: str
    menu_border: str
    menu_text: str
    menu_hover: str
    menu_disabled: str
    text_main: str
    text_sub: str
    text_dim: str
    text_warn: str
    text_disabled: str
    accent: str
    overlay_rgb: str  # 반투명 덧칠(hover / 테두리 / 구분선) 색 "r,g,b" - 다크는 흰색, 라이트는 검정
    font_family: str = FALLBACK_FONTS
    left_scale: int = 100  # 좌패널 글자 배율(%)
    todo_scale: int = 100  # 우패널(TODO) 글자 배율(%)
    todo_text: str = ""  # TODO 글자색 ("" 이면 text_main)
    fade_text: bool = False  # 투명도 슬라이더가 글자까지 투명하게 (False: 배경만)
    popup_width: int = 260  # 리마인더 알림 창 폭(px)
    popup_scale: int = 100  # 리마인더 알림 창 글자 배율(%)

    def overlay(self, alpha: int) -> str:
        return f"rgba({self.overlay_rgb},{alpha})"

    def overlay_color(self, alpha: int) -> QColor:
        r, g, b = map(int, self.overlay_rgb.split(","))
        return QColor(r, g, b, alpha)

    def accent_rgba(self, alpha: int) -> str:
        c = QColor(self.accent)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"

    @property
    def line(self) -> str:
        return self.overlay(40)

    @property
    def accent_hover(self) -> str:
        return QColor(self.accent).lighter(115).name()

    @property
    def on_accent(self) -> str:
        """강조색 위의 글자색 - 밝은 강조색이면 어둡게"""
        return "#1a1a1a" if QColor(self.accent).lightnessF() > 0.7 else "white"

    @property
    def todo_color(self) -> str:
        return self.todo_text or self.text_main


DARK = Theme(
    dark=True,
    bg="#141414",
    popup_bg="#202020",
    dialog_bg="#242426",
    menu_bg="#2b2b2b",
    menu_border="#4a4a4a",
    menu_text="#f0f0f0",
    menu_hover="rgba(255,255,255,40)",
    menu_disabled="#6d6d6d",
    text_main="#f0f0f0",
    text_sub="#9e9e9e",
    text_dim="#5f5f5f",
    text_warn="#ff8a65",
    text_disabled="#6d6d6d",
    accent="#4a7bd0",
    overlay_rgb="255,255,255",
)

LIGHT = Theme(
    dark=False,
    bg="#f3f3f5",
    popup_bg="#ffffff",
    dialog_bg="#ffffff",
    menu_bg="#ffffff",
    menu_border="#cfcfd4",
    menu_text="#1e1e1e",
    menu_hover="rgba(0,0,0,40)",
    menu_disabled="#a0a0a0",
    text_main="#1e1e1e",
    text_sub="#6a6a6a",
    text_dim="#a9a9a9",
    text_warn="#e0552d",
    text_disabled="#a0a0a0",
    accent="#4a7bd0",
    overlay_rgb="0,0,0",
)

MENU_FIELDS = ("menu_bg", "menu_border", "menu_text", "menu_hover", "menu_disabled")

_current = DARK


def current() -> Theme:
    return _current


def set_current(theme: Theme):
    global _current
    _current = theme


def system_dark() -> bool:
    """OS 가 다크 모드인지 ("system" 테마). 알 수 없으면 다크로 본다."""
    return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light


def _mix(color: str, rgb: str, ratio: float) -> str:
    """color 를 rgb 쪽으로 ratio 만큼 섞는다."""
    c = QColor(color)
    r, g, b = map(int, rgb.split(","))
    return QColor(
        round(c.red() + (r - c.red()) * ratio),
        round(c.green() + (g - c.green()) * ratio),
        round(c.blue() + (b - c.blue()) * ratio),
    ).name()


def build(appearance: dict, system_dark: bool = True) -> Theme:
    """appearance: widget_config.appearance(cfg) 결과 / system_dark: "system" 테마일 때 OS 가 다크인지"""
    name = appearance["theme"]
    named = DARK if name == "dark" or (name == "system" and system_dark) else LIGHT
    base = named
    bg = appearance["background"]
    if bg:
        # 배경색을 고르면 글자 / 덧칠 색은 테마 대신 배경 밝기를 따른다 (어두운 배경에 어두운 글자가 되지 않게)
        base = DARK if QColor(bg).lightnessF() < 0.5 else LIGHT
    changes = {
        # 우클릭 메뉴는 위젯 밖에 뜨므로 배경색이 아니라 테마 설정을 따른다 (다크면 늘 어둡게)
        **{field: getattr(named, field) for field in MENU_FIELDS},
        "accent": appearance["accent"],
        "left_scale": appearance["left_scale"],
        "todo_scale": appearance["todo_scale"],
        "todo_text": appearance["todo_text_color"],
        "fade_text": appearance["fade_text"],
        "popup_width": appearance["popup_width"],
        "popup_scale": appearance["popup_scale"],
    }
    family = appearance["font_family"].replace("'", "")
    if family:
        changes["font_family"] = f"'{family}', {FALLBACK_FONTS}"
    if bg:
        # 팝업 / 확인 창은 위젯 배경보다 조금 덧칠한 색 (다크 기본값의 20 -> 32 / 36 과 같은 비율)
        changes["bg"] = bg
        changes["popup_bg"] = _mix(bg, base.overlay_rgb, 0.05)
        changes["dialog_bg"] = _mix(bg, base.overlay_rgb, 0.07)
    return replace(base, **changes)


def px(base: int, scale: int) -> int:
    """배율(%)을 적용한 글자 크기(px)"""
    return round(base * scale / 100)


# 위젯 밖에 뜨는 팝업(QMenu 등)의 공통 스타일.
# 위젯 / 설정창 스타일시트에도 넣어 두면 입력칸의 기본 우클릭 메뉴(잘라내기 / 붙여넣기)까지 적용된다.
def menu_style(t: Theme) -> str:
    return f"""
    QMenu {{
        background-color: {t.menu_bg};
        color: {t.menu_text};
        font-family: {t.font_family};
        border: 1px solid {t.menu_border};
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 20px; background: transparent; }}
    QMenu::item:selected {{ background-color: {t.menu_hover}; }}
    QMenu::item:disabled {{ color: {t.menu_disabled}; }}
    QMenu::separator {{
        height: 1px;
        background: {t.menu_border};
        margin: 6px 4px;
    }}
"""


def button_style(t: Theme, font_px: int = 12) -> str:
    return f"""
    QPushButton {{
        background: {t.overlay(26)};
        color: {t.text_main};
        font-family: {t.font_family};
        font-size: {font_px}px;
        border: 1px solid {t.overlay(40)};
        border-radius: 6px;
        padding: 7px 0px;
    }}
    QPushButton:focus {{ outline: none; }}
    QPushButton:hover {{ background: {t.overlay(46)}; }}
    QPushButton:pressed {{ background: {t.overlay(66)}; }}
    QPushButton:disabled {{
        background: {t.overlay(10)};
        color: {t.text_disabled};
        border: 1px solid {t.overlay(18)};
    }}
"""


# 팝업(ReminderPicker / TaskPicker) 안의 콤보박스 / 입력칸 공통 스타일
def popup_form_style(t: Theme) -> str:
    return f"""
    QComboBox, QLineEdit {{
        background: {t.overlay(18)};
        color: {t.text_main};
        font-family: {t.font_family};
        font-size: 12px;
        border: 1px solid {t.overlay(40)};
        border-radius: 6px;
        padding: 3px 8px;
        selection-background-color: {t.accent};
        selection-color: {t.on_accent};
    }}
    QLineEdit:focus {{ border: 1px solid {t.overlay(90)}; }}
    QComboBox::drop-down {{ border: none; width: 0px; }}
    QComboBox QAbstractItemView {{
        background: {t.menu_bg};
        color: {t.menu_text};
        font-family: {t.font_family};
        font-size: 12px;
        selection-background-color: {t.accent};
        border: 1px solid {t.menu_border};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{ padding: 3px 8px; }}
    QComboBox QAbstractItemView::item:selected {{
        background: {t.accent};
        color: {t.on_accent};
    }}
    QComboBox QAbstractItemView QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QComboBox QAbstractItemView QScrollBar::handle:vertical {{
        background: {t.overlay(50)};
        border-radius: 3px;
        min-height: 20px;
    }}
    QComboBox QAbstractItemView QScrollBar::add-line:vertical,
    QComboBox QAbstractItemView QScrollBar::sub-line:vertical {{ height: 0px; }}
    QComboBox QAbstractItemView QScrollBar::add-page:vertical,
    QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{ background: none; }}
"""

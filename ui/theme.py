"""위젯 공통 테마 (clock_widget / todo_panel / reminder_* 가 함께 사용)"""

from PySide6.QtGui import QColor


# 배경은 불투명 - 위젯 투명도는 위젯의 투명도 슬라이더(setWindowOpacity)로만 정한다
BG_COLOR = QColor(20, 20, 20)  # 위젯 배경 (paintEvent)
POPUP_BG_COLOR = QColor(32, 32, 32)  # 팝업 배경
CORNER_RADIUS = 14

TEXT_MAIN = "#f0f0f0"
TEXT_SUB = "#9e9e9e"
TEXT_DIM = "#5f5f5f"
TEXT_WARN = "#ff8a65"
ACCENT = "#4a7bd0"
LINE_COLOR = "rgba(255,255,255,40)"
FONT_FAMILY = "'Malgun Gothic', 'Segoe UI', sans-serif"

# 위젯 밖에 뜨는 팝업(QMenu 등)의 공통 스타일
MENU_STYLE = f"""
    QMenu {{
        background-color: #2b2b2b;
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        border: 1px solid #4a4a4a;
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 20px; }}
    QMenu::item:selected {{ background-color: rgba(255,255,255,40); }}
    QMenu::separator {{
        height: 1px;
        background: #4a4a4a;
        margin: 6px 4px;
    }}
"""

BUTTON_STYLE = f"""
    QPushButton {{
        background: rgba(255,255,255,26);
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        font-size: 12px;
        border: 1px solid rgba(255,255,255,40);
        border-radius: 6px;
        padding: 7px 0px;
    }}
    QPushButton:hover {{ background: rgba(255,255,255,46); }}
    QPushButton:pressed {{ background: rgba(255,255,255,66); }}
    QPushButton:disabled {{
        background: rgba(255,255,255,10);
        color: #6d6d6d;
        border: 1px solid rgba(255,255,255,18);
    }}
"""

# 팝업(ReminderPicker / TaskPicker) 안의 콤보박스 / 입력칸 공통 스타일
POPUP_FORM_STYLE = f"""
    QComboBox, QLineEdit {{
        background: rgba(255,255,255,18);
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        font-size: 12px;
        border: 1px solid rgba(255,255,255,40);
        border-radius: 6px;
        padding: 3px 8px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus {{ border: 1px solid rgba(255,255,255,90); }}
    QComboBox::drop-down {{ border: none; width: 0px; }}
    QComboBox QAbstractItemView {{
        background: #2b2b2b;
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        font-size: 12px;
        selection-background-color: {ACCENT};
        border: 1px solid #4a4a4a;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{ padding: 3px 8px; }}
    QComboBox QAbstractItemView::item:selected {{
        background: {ACCENT};
        color: white;
    }}
    QComboBox QAbstractItemView QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QComboBox QAbstractItemView QScrollBar::handle:vertical {{
        background: rgba(255,255,255,50);
        border-radius: 3px;
        min-height: 20px;
    }}
    QComboBox QAbstractItemView QScrollBar::add-line:vertical,
    QComboBox QAbstractItemView QScrollBar::sub-line:vertical {{ height: 0px; }}
    QComboBox QAbstractItemView QScrollBar::add-page:vertical,
    QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{ background: none; }}
"""

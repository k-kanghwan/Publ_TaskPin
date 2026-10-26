"""색 선택 창 (설정창 강조색 / 배경색 / 글자색, 태그 추가 창이 함께 사용)"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog


def pick_color(initial: str, title: str) -> str:
    """색 선택 창. 고른 색 "#rrggbb", 취소하면 "".
    부르는 창의 스타일시트(밝은 글자 등)가 번지지 않도록 부모 없이 띄우고,
    항상 위에 둔 창(설정창 / 위젯)보다 위에 둔다."""
    dialog = QColorDialog(QColor(initial))
    dialog.setWindowTitle(title)
    dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    if dialog.exec() != QColorDialog.Accepted:
        return ""
    return dialog.selectedColor().name()

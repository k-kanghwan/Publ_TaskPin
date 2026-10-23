"""위젯 테마의 확인 창 (QMessageBox 대신)

어두운 배경은 위젯과 같게 두고, 밝은 테두리 / 큰 글씨로 바탕화면 위에서도 잘 보이게 한다.
필요하면 강조 값(예: 남은시간)을 크게 한 줄 보여준다.

키보드
  - Enter : 확인 버튼, Esc : 취소
"""

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    ACCENT,
    BUTTON_STYLE,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_MAIN,
    TEXT_SUB,
    TEXT_WARN,
)


DIALOG_WIDTH = 260
DIALOG_BG_COLOR = QColor(36, 36, 38)  # 위젯 배경(20)보다 살짝 밝게 - 위젯 위에 떠 보이도록
DIALOG_BORDER_COLOR = QColor(74, 123, 208, 210)  # ACCENT


class ConfirmDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        confirm_text: str = "확인",
        value_caption: str = "",
        value: str = "",
        note: str = "",
        danger: bool = False,
        parent=None,
    ):
        """
        Parameters
        ----------
        value_caption / value : 크게 보여줄 값과 그 이름 (비우면 표시 안 함)
        note : 메시지 아래 흐린 보조 설명
        danger : 확인 버튼을 경고색으로 (해제/삭제 같은 동작)
        """
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)

        confirm_color = TEXT_WARN if danger else ACCENT
        self.setStyleSheet(
            BUTTON_STYLE
            + f"""
            QLabel {{
                background: transparent;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY};
            }}
            QPushButton {{ padding: 6px 0px; }}
            QPushButton#confirm {{
                background: {confirm_color};
                color: #1a1a1a;
                font-weight: bold;
                border: 1px solid {confirm_color};
            }}
            QPushButton#confirm:hover {{ background: white; border: 1px solid white; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        root.addWidget(title_label)

        if value:
            value_box = QVBoxLayout()
            value_box.setSpacing(0)
            value_label = QLabel(value)
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("font-size: 26px; font-weight: bold;")
            caption = QLabel(value_caption)
            caption.setAlignment(Qt.AlignCenter)
            caption.setStyleSheet(f"font-size: 11px; color: {TEXT_SUB};")
            value_box.addWidget(value_label)
            value_box.addWidget(caption)
            root.addLayout(value_box)

        message_label = QLabel(message)
        message_label.setTextFormat(Qt.PlainText)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 13px;")
        root.addWidget(message_label)

        if note:
            note_label = QLabel(note)
            note_label.setTextFormat(Qt.PlainText)
            note_label.setWordWrap(True)
            note_label.setStyleSheet(f"font-size: 11px; color: {TEXT_SUB};")
            root.addWidget(note_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_cancel = QPushButton("취소")
        self.btn_confirm = QPushButton(confirm_text)
        self.btn_confirm.setObjectName("confirm")
        self.btn_confirm.setDefault(True)  # Enter
        for btn in (self.btn_cancel, self.btn_confirm):
            btn.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(btn)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm.clicked.connect(self.accept)
        root.addSpacing(2)
        root.addLayout(buttons)

    def paintEvent(self, event):
        # 반투명 최상위 창은 스타일시트 배경이 그려지지 않으므로 직접 그린다
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, DIALOG_BG_COLOR)
        painter.setPen(DIALOG_BORDER_COLOR)
        painter.drawPath(path)

    def exec_over(self, anchor: QWidget) -> bool:
        """anchor(위젯) 가운데에 띄우고 화면 안쪽으로 맞춘 뒤 결과를 돌려준다."""
        self.adjustSize()
        center = anchor.mapToGlobal(anchor.rect().center())
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = center.x() - self.width() // 2
        y = center.y() - self.height() // 2
        x = min(max(x, area.left()), area.right() + 1 - self.width())
        y = min(max(y, area.top()), area.bottom() + 1 - self.height())
        self.move(QPoint(x, y))
        return self.exec() == QDialog.Accepted

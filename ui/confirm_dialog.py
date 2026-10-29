"""위젯 테마의 확인 창 (QMessageBox 대신)

배경은 위젯 테마를 따르고, 강조색 테두리 / 큰 글씨로 바탕화면 위에서도 잘 보이게 한다.
필요하면 강조 값(예: 남은시간)을 크게 한 줄 보여준다.
되돌릴 수 없는 동작(모든 데이터 초기화)은 confirm_phrase 를 똑같이 입력해야 확인 버튼이 켜진다
(git 저장소를 지울 때 이름을 입력하게 하는 것처럼).

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

from ui import painted, theme
from ui.painted import CheckBox
from ui.text_input import PreeditLineEdit
from ui.theme import CORNER_RADIUS

DIALOG_WIDTH = 260
BORDER_ALPHA = 210  # 강조색 테두리


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
        remember_text: str = "",
        confirm_phrase: str = "",
        parent=None,
    ):
        """
        Parameters
        ----------
        value_caption / value : 크게 보여줄 값과 그 이름 (비우면 표시 안 함)
        note : 메시지 아래 흐린 보조 설명
        danger : 확인 버튼을 경고색으로 (삭제 같은 동작)
        remember_text : 버튼 위 체크박스 (예: "다시 묻지 않음") - 확인했을 때 remembered() 로 읽는다
        confirm_phrase : 이 문구를 똑같이 입력해야 확인 버튼이 켜진다 (입력칸을 버튼 위에 둔다)
        """
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)

        t = self._theme = theme.current()
        confirm_color = t.text_warn if danger else t.accent
        confirm_hover = QColor(confirm_color).lighter(125).name()
        self.setStyleSheet(
            theme.button_style(t)
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QPushButton {{ padding: 6px 0px; }}
            QPushButton#confirm {{ color: #1a1a1a; font-weight: bold; }}
            QPushButton#confirm:disabled {{ color: {t.text_disabled}; }}
            QCheckBox {{
                background: transparent;
                color: {t.text_sub};
                font-family: {t.font_family};
                font-size: 12px;
            }}
            """
            + theme.popup_form_style(t)
        )

        painted.set_boxes(
            self,
            [
                (
                    QPushButton,
                    "confirm",
                    painted.accent_box(t, confirm_color, confirm_hover),
                ),
                (QPushButton, None, painted.button_box(t)),
                *painted.form_rules(t),
            ],
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
            caption.setStyleSheet(f"font-size: 11px; color: {t.text_sub};")
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
            note_label.setStyleSheet(f"font-size: 11px; color: {t.text_sub};")
            root.addWidget(note_label)

        self._remember = None
        if remember_text:
            self._remember = CheckBox(remember_text)  # 네모는 직접 그린다 (ui/painted)
            self._remember.setCursor(Qt.PointingHandCursor)
            root.addWidget(self._remember)

        # 조합 중인 한글까지 맞춰 본다 (마지막 글자는 확정 전까지 text() 에 없다)
        self._phrase = confirm_phrase
        self._phrase_edit = None
        if confirm_phrase:
            self._phrase_edit = PreeditLineEdit()
            self._phrase_edit.setPlaceholderText(confirm_phrase)
            self._phrase_edit.textChanged.connect(self._update_confirm)
            self._phrase_edit.preedit_changed.connect(self._update_confirm)
            root.addWidget(self._phrase_edit)

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
        self._update_confirm()

    def _update_confirm(self):
        """confirm_phrase 를 똑같이 입력했을 때만 확인 버튼을 켠다."""
        if self._phrase_edit is not None:
            typed = self._phrase_edit.full_text().strip()
            self.btn_confirm.setEnabled(typed == self._phrase)

    def remembered(self) -> bool:
        """remember_text 체크박스를 켰는지"""
        return self._remember is not None and self._remember.isChecked()

    def paintEvent(self, event):
        # 반투명 최상위 창은 스타일시트 배경이 그려지지 않으므로 직접 그린다
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CORNER_RADIUS,
            CORNER_RADIUS,
        )
        painter.fillPath(path, QColor(self._theme.dialog_bg))
        border = QColor(self._theme.accent)
        border.setAlpha(BORDER_ALPHA)
        painter.setPen(border)
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
        if self._phrase_edit is not None:
            self._phrase_edit.setFocus()
        return self.exec() == QDialog.Accepted

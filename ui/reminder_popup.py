"""리마인더 알림 팝업 (obsidian-reminder 의 [Mark as Done] / [Remind Me Later] 와 동일한 역할)

트레이 풍선 알림은 버튼을 달 수 없으므로 위젯 옆에 이 팝업을 함께 띄운다.
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.theme import CORNER_RADIUS


POPUP_WIDTH = 260


def snooze_targets(now: datetime) -> list:
    """ "나중에 알림" 선택지 [(표시, 시각)]"""
    tomorrow_9 = (now + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    return [
        ("5분 후", now + timedelta(minutes=5)),
        ("15분 후", now + timedelta(minutes=15)),
        ("1시간 후", now + timedelta(hours=1)),
        ("내일 09:00", tomorrow_9),
    ]


class ReminderPopup(QWidget):
    done_requested = Signal(str)  # item id
    snooze_requested = Signal(str, object)  # item id, datetime

    def __init__(self, item_id: str, text: str, due: datetime):
        super().__init__()
        self.item_id = item_id

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedWidth(POPUP_WIDTH)

        t = self._theme = theme.current()
        self.setStyleSheet(
            theme.button_style(t)
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QPushButton {{ padding: 5px 0px; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("⏰ 리마인더")
        title.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {t.text_warn};"
        )
        when = QLabel(due.strftime("%m/%d %H:%M"))
        when.setStyleSheet(f"font-size: 11px; color: {t.text_sub};")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(when)
        root.addLayout(header)

        body = QLabel(text or "(내용 없음)")
        body.setTextFormat(Qt.PlainText)
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 13px;")
        root.addWidget(body)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        btn_done = QPushButton("완료")
        btn_later = QPushButton("나중에 ▾")
        btn_close = QPushButton("닫기")
        for btn in (btn_done, btn_later, btn_close):
            btn.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(btn)
        btn_done.clicked.connect(self._on_done)
        btn_later.clicked.connect(lambda: self._show_snooze_menu(btn_later))
        btn_close.clicked.connect(self.close)
        root.addLayout(buttons)

        self.adjustSize()

    def _on_done(self):
        self.done_requested.emit(self.item_id)
        self.close()

    def _show_snooze_menu(self, anchor: QPushButton):
        menu = QMenu(self)
        menu.setStyleSheet(theme.menu_style(self._theme))
        for label, until in snooze_targets(datetime.now().astimezone()):
            menu.addAction(label, lambda u=until: self._on_snooze(u))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _on_snooze(self, until: datetime):
        self.snooze_requested.emit(self.item_id, until)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QColor(self._theme.popup_bg))

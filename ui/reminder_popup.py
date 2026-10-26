"""리마인더 알림 팝업 (obsidian-reminder 의 [Mark as Done] / [Remind Me Later] 와 동일한 역할)

트레이 풍선 알림은 버튼을 달 수 없으므로 위젯 옆에 이 팝업을 함께 띄운다.
폭과 글자 크기는 설정창 Appearance "알림 창"(theme.popup_width / popup_scale)을 따른다.
설정창은 preview=True 로 같은 팝업을 실제 크기 그대로 예시로 넣는다.
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
from ui.theme import CORNER_RADIUS, px


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

    def __init__(
        self,
        item_id: str,
        text: str,
        due: datetime,
        look: theme.Theme = None,
        preview: bool = False,
        parent=None,
    ):
        """look: 그릴 테마 (None 이면 theme.current())
        preview: 설정창 예시 - 창이 아니라 parent 안의 자식으로, 눌러도 반응하지 않는다"""
        super().__init__(parent)
        self.item_id = item_id

        if preview:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_DeleteOnClose, True)

        t = self._theme = look or theme.current()
        s = t.popup_scale
        self.setFixedWidth(t.popup_width)
        self.setStyleSheet(
            theme.button_style(t, px(12, s))
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QPushButton {{ padding: {px(5, s)}px 0px; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("⏰ 리마인더")
        title.setStyleSheet(
            f"font-size: {px(12, s)}px; font-weight: bold; color: {t.text_warn};"
        )
        when = QLabel(due.strftime("%m/%d %H:%M"))
        when.setStyleSheet(f"font-size: {px(11, s)}px; color: {t.text_sub};")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(when)
        root.addLayout(header)

        body = QLabel(text or "(내용 없음)")
        body.setTextFormat(Qt.PlainText)
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: {px(13, s)}px;")
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

        # 높이는 폭에 맞춰 줄바꿈한 내용 높이로 정한다. adjustSize() 는 줄바꿈 라벨의 높이를
        # 넉넉하게 어림해 빈 줄이 생기고, 설정창 예시(레이아웃 안)와 크기가 달라진다
        self.setFixedHeight(self.heightForWidth(t.popup_width))

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

"""좌패널 업무 이력 (가로 모드에서 시작 / 종료 아래) - "멍청한 뷰"

TaskPinApp 이 task_store.history 로 읽은 지난 Task 를 set_entries 로 넘기면 날짜 머리줄 아래에
"09:00–10:30  업무명  결과" 줄로 쌓는다. 넘치면 스크롤한다. 클릭 동작은 없고 툴팁에 상세 업무.
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from manager import task_store
from ui import theme
from ui.theme import px

WEEKDAYS = "월화수목금토일"
RESULT_TEXT = {
    task_store.COMPLETED: "완료",
    task_store.RELEASED: "해제",
    task_store.EXPIRED: "지남",
}
EMPTY_TEXT = "지난 Task가 없습니다"
ROW_SPACING = 2


def day_caption(day, today) -> str:
    """날짜 머리줄: 오늘 / 어제 / 11/26 (수)"""
    delta = (today - day).days
    if delta == 0:
        return "오늘"
    if delta == 1:
        return "어제"
    return f"{day:%m/%d} ({WEEKDAYS[day.weekday()]})"


def time_range(entry) -> str:
    """09:00–10:30 (자정을 넘긴 Task 도 시각만)"""
    return f"{entry.start_at:%H:%M}–{entry.end_at:%H:%M}"


class _ElideLabel(QLabel):
    """받은 폭에 맞춰 한 줄로 말줄임하는 라벨 (레이아웃이 폭을 정함)"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._full = text
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.elide()

    def elide(self):
        self.setText(
            self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(0, self.width()))
        )


class _Row(QWidget):
    """한 줄: 시각 · 업무명(폭에 맞춰 말줄임) · 결과"""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.time = QLabel(time_range(entry), self)
        self.title = _ElideLabel(entry.title or "(업무명 없음)", self)
        self.result = QLabel(RESULT_TEXT[entry.result], self)
        layout.addWidget(self.time)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.result)
        tip = [entry.title or "(업무명 없음)", f"{time_range(entry)} · {RESULT_TEXT[entry.result]}"]
        if entry.detail:
            tip += ["", entry.detail]
        self.setToolTip("\n".join(tip))

    def apply_style(self, t, size: int):
        base = f"font-size: {size}px; font-family: {t.font_family};"
        self.time.setStyleSheet(base + f" color: {t.text_sub};")
        self.title.setStyleSheet(
            base + f" color: {t.text_main if self.entry.title else t.text_dim};"
        )
        color = {
            task_store.COMPLETED: t.accent,
            task_store.RELEASED: t.text_warn,
        }.get(self.entry.result, t.text_dim)
        self.result.setStyleSheet(base + f" color: {color};")
        self.title.ensurePolished()  # 스타일시트 글꼴로 말줄임 폭을 잰다
        self.title.elide()


class TaskHistory(QWidget):
    """캡션 "업무 이력" + 스크롤 목록"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []
        self._today = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.caption = QLabel("업무 이력", self)
        root.addWidget(self.caption)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll.verticalScrollBar().setFocusPolicy(Qt.NoFocus)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(ROW_SPACING)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)
        # 위젯 최소 높이를 크게 늘리지 않게: 캡션 + 한 줄 정도면 된다
        self.scroll.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setHeight(self.caption.sizeHint().height() + 4 + self.fontMetrics().height())
        return hint

    def set_entries(self, entries, now: datetime):
        """최신 순 지난 Task 로 목록을 다시 만든다 (최대 50줄이라 매번 새로 만들어도 가볍다)."""
        self._entries = list(entries)
        self._today = now.date()
        self._rebuild()

    def _rebuild(self):
        layout = self.list_layout
        while layout.count() > 1:  # 맨 뒤 stretch 만 남긴다
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        t = theme.current()
        size = px(11, t.left_scale)
        if not self._entries:
            empty = QLabel(EMPTY_TEXT, self.container)
            empty.setStyleSheet(
                f"font-size: {size}px; font-family: {t.font_family}; color: {t.text_dim};"
            )
            layout.insertWidget(0, empty)
            return
        index = 0
        day = None
        for entry in self._entries:
            if entry.start_at.date() != day:
                day = entry.start_at.date()
                head = QLabel(day_caption(day, self._today), self.container)
                head.setStyleSheet(
                    f"font-size: {size}px; font-family: {t.font_family};"
                    f" color: {t.text_dim}; padding-top: {2 if index else 0}px;"
                )
                layout.insertWidget(index, head)
                index += 1
            row = _Row(entry, self.container)
            row.apply_style(t, size)
            layout.insertWidget(index, row)
            index += 1

    def apply_appearance(self):
        t = theme.current()
        self.caption.setStyleSheet(
            f"font-size: {px(11, t.left_scale)}px; font-family: {t.font_family};"
            f" color: {t.text_sub};"
        )
        self.setStyleSheet(
            f"""
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0px; }}
            QScrollBar::handle:vertical {{
                background: {t.overlay(50)};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            """
        )
        if self._today is not None:
            self._rebuild()

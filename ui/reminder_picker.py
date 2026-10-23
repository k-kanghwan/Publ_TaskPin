"""`(@` 입력 시 뜨는 리마인더 날짜/시간 피커

obsidian-reminder 의 피커 레이아웃(달력 + 선택일 리마인더 목록 + 시간 + OK)을
위젯 다크 테마로 옮겼다. QCalendarWidget 은 다크 스타일링이 어려워 그리드를 직접 만든다.

키보드
  - ←/→ : 하루, ↑/↓ : 일주일, PageUp/PageDown : 한 달
  - Shift+↑/↓ : 시간 15분
  - Enter : 확인, Esc / 바깥 클릭 : 취소
"""

import calendar
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    ACCENT,
    FONT_FAMILY,
    LINE_COLOR,
    POPUP_BG_COLOR,
    POPUP_FORM_STYLE,
    TEXT_DIM,
    TEXT_MAIN,
    TEXT_SUB,
)


TIME_STEP_MIN = 15
DEFAULT_TIME = "09:00"
WEEKDAYS = ("일", "월", "화", "수", "목", "금", "토")
SUNDAY_COLOR = "#e57373"
SATURDAY_COLOR = "#64b5f6"
MAX_LISTED = 4  # 선택일 리마인더 목록 최대 표시 수


def next_slot(now: datetime) -> datetime:
    """지금 이후의 다음 15분 슬롯"""
    base = now.replace(second=0, microsecond=0)
    return base + timedelta(minutes=TIME_STEP_MIN - base.minute % TIME_STEP_MIN)


class ReminderPicker(QFrame):
    picked = Signal(object)  # datetime
    closed = Signal()  # 확인/취소와 관계없이 닫힐 때

    def __init__(self, initial: datetime = None, reminders=None, parent=None):
        """
        Parameters
        ----------
        initial : 이미 토큰이 있을 때 그 값으로 시작
        reminders : [(datetime, 본문)] - 선택일 목록과 달력 표시에 사용
        """
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 둥근 모서리 바깥을 투명하게 (배경은 스타일시트가 그림)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._reminders = sorted(reminders or [], key=lambda r: r[0])
        self._time_touched = initial is not None

        if initial is None:
            initial = next_slot(datetime.now())
        self._selected = initial.date()
        self._month = self._selected.replace(day=1)

        self._build_ui()
        self._set_time(initial.strftime("%H:%M"))
        self._refresh()

    # ==================================================
    # UI 구성
    # ==================================================
    def _build_ui(self):
        self.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY};
                font-size: 12px;
            }}
            QPushButton {{
                background: transparent;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY};
                font-size: 12px;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,30); }}
            QPushButton#ok {{
                background: {ACCENT};
                color: white;
                padding: 4px 14px;
            }}
            QPushButton#ok:hover {{ background: #5b8be0; }}
            """
            + POPUP_FORM_STYLE
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # ---- 헤더: < 2026년 10월 > ----
        header = QHBoxLayout()
        self.btn_prev = self._nav_button("<", lambda: self._shift_month(-1))
        self.btn_next = self._nav_button(">", lambda: self._shift_month(1))
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        header.addWidget(self.btn_prev)
        header.addWidget(self.month_label, 1)
        header.addWidget(self.btn_next)
        root.addLayout(header)

        # ---- 달력 그리드 ----
        grid = QGridLayout()
        grid.setSpacing(2)
        for col, name in enumerate(WEEKDAYS):
            lb = QLabel(name)
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {self._weekday_color(col)};"
            )
            grid.addWidget(lb, 0, col)

        self._day_buttons = []
        for i in range(42):
            btn = QPushButton()
            btn.setFixedSize(30, 26)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._on_day_clicked(idx))
            grid.addWidget(btn, 1 + i // 7, i % 7)
            self._day_buttons.append(btn)
        root.addLayout(grid)

        root.addWidget(self._separator())

        # ---- 선택일 리마인더 목록 ----
        self.list_label = QLabel()
        self.list_label.setTextFormat(Qt.PlainText)
        self.list_label.setWordWrap(True)
        root.addWidget(self.list_label)

        # ---- 시간 + OK ----
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        time_caption = QLabel("시간")
        time_caption.setStyleSheet(f"color: {TEXT_SUB};")

        self.time_combo = QComboBox()
        self.time_combo.setFocusPolicy(Qt.NoFocus)
        self.time_combo.setMaxVisibleItems(8)
        for minutes in range(0, 24 * 60, TIME_STEP_MIN):
            self.time_combo.addItem(f"{minutes // 60:02}:{minutes % 60:02}")
        self.time_combo.activated.connect(self._on_time_activated)
        # 팝업 목록은 기본적으로 콤보 폭과 같아서 스크롤바에 밀려 "1...0" 처럼 잘린다
        view = self.time_combo.view()
        view.setTextElideMode(Qt.ElideNone)
        view.setMinimumWidth(view.fontMetrics().horizontalAdvance("00:00") + 40)

        btn_ok = QPushButton("확인")
        btn_ok.setObjectName("ok")
        btn_ok.setFocusPolicy(Qt.NoFocus)
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self._accept)

        bottom.addWidget(time_caption)
        bottom.addWidget(self.time_combo)
        bottom.addStretch(1)
        bottom.addWidget(btn_ok)
        root.addLayout(bottom)

    def _nav_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(26, 24)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {LINE_COLOR}; border: none;")
        return line

    @staticmethod
    def _weekday_color(col: int) -> str:
        return {0: SUNDAY_COLOR, 6: SATURDAY_COLOR}.get(col, TEXT_SUB)

    # ==================================================
    # 상태 갱신
    # ==================================================
    def _grid_start(self) -> date:
        """그리드 첫 칸(일요일) 날짜"""
        # date.weekday(): 월=0 ... 일=6  ->  일요일 시작 열 번호로 변환
        offset = (self._month.weekday() + 1) % 7
        return self._month - timedelta(days=offset)

    def _refresh(self):
        self.month_label.setText(f"{self._month.year}년 {self._month.month}월")

        today = date.today()
        reminder_days = {dt.date() for dt, _ in self._reminders}
        start = self._grid_start()
        for i, btn in enumerate(self._day_buttons):
            day = start + timedelta(days=i)
            btn.setText(str(day.day))

            if day == self._selected:
                color, bg, border = "white", ACCENT, ACCENT
            else:
                in_month = day.month == self._month.month
                color = self._weekday_color(i % 7) if in_month else TEXT_DIM
                if in_month and i % 7 not in (0, 6):
                    color = TEXT_MAIN
                bg = "transparent"
                border = TEXT_SUB if day == today else "transparent"
            weight = "bold" if day in reminder_days else "normal"
            hover = ACCENT if day == self._selected else "rgba(255,255,255,30)"
            btn.setStyleSheet(
                f"QPushButton {{ color: {color}; background: {bg};"
                f" border: 1px solid {border}; font-weight: {weight}; }}"
                f" QPushButton:hover {{ background: {hover}; }}"
            )

        listed = [
            (dt, text) for dt, text in self._reminders if dt.date() == self._selected
        ]
        if listed:
            lines = [f"{dt:%H:%M}  {text}" for dt, text in listed[:MAX_LISTED]]
            if len(listed) > MAX_LISTED:
                lines.append(f"... 외 {len(listed) - MAX_LISTED}건")
            self.list_label.setText("\n".join(lines))
            self.list_label.setStyleSheet(f"color: {TEXT_MAIN};")
        else:
            self.list_label.setText("리마인더 없음")
            self.list_label.setStyleSheet(f"color: {TEXT_SUB}; font-style: italic;")

    def _select(self, day: date):
        self._selected = day
        self._month = day.replace(day=1)
        if not self._time_touched:
            # 시간을 직접 고르지 않았다면 오늘은 다음 슬롯, 다른 날은 기본 시각
            if day == date.today():
                self._set_time(next_slot(datetime.now()).strftime("%H:%M"))
            else:
                self._set_time(DEFAULT_TIME)
        self._refresh()

    def _shift_month(self, delta: int):
        year, month = divmod(self._month.year * 12 + self._month.month - 1 + delta, 12)
        last_day = calendar.monthrange(year, month + 1)[1]
        self._select(date(year, month + 1, min(self._selected.day, last_day)))

    def _on_day_clicked(self, idx: int):
        self._select(self._grid_start() + timedelta(days=idx))

    def _set_time(self, hhmm: str):
        idx = self.time_combo.findText(hhmm)
        if idx < 0:  # 15분 단위가 아닌 기존 토큰 -> 가장 가까운 이전 슬롯
            h, m = map(int, hhmm.split(":"))
            idx = (h * 60 + m) // TIME_STEP_MIN
        self.time_combo.setCurrentIndex(idx)

    def _on_time_activated(self, _idx: int):
        self._time_touched = True
        self.setFocus()  # 콤보 선택 후에도 방향키/Enter 가 피커로 오도록

    # ==================================================
    # 결과
    # ==================================================
    def selected_datetime(self) -> datetime:
        hh, mm = map(int, self.time_combo.currentText().split(":"))
        return datetime.combine(self._selected, datetime.min.time()).replace(
            hour=hh, minute=mm
        )

    def _accept(self):
        self.picked.emit(self.selected_datetime())
        self.close()

    def keyPressEvent(self, event):
        key = event.key()
        shift = event.modifiers() & Qt.ShiftModifier
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
        elif key == Qt.Key_Escape:
            self.close()
        elif shift and key in (Qt.Key_Up, Qt.Key_Down):
            step = -1 if key == Qt.Key_Up else 1
            idx = (self.time_combo.currentIndex() + step) % self.time_combo.count()
            self.time_combo.setCurrentIndex(idx)
            self._time_touched = True
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            days = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -7, Qt.Key_Down: 7}
            self._select(self._selected + timedelta(days=days[key]))
        elif key == Qt.Key_PageUp:
            self._shift_month(-1)
        elif key == Qt.Key_PageDown:
            self._shift_month(1)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def paintEvent(self, event):
        # 반투명 최상위 창은 스타일시트 배경이 그려지지 않으므로 직접 그린다
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.fillPath(path, POPUP_BG_COLOR)
        painter.setPen(QColor(74, 74, 74))
        painter.drawPath(path)

    # ==================================================
    # 표시 위치
    # ==================================================
    def popup_for(self, anchor: QWidget):
        """anchor 바로 아래(공간이 없으면 위)에 띄운다."""
        self.adjustSize()
        below = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        screen = QApplication.screenAt(below) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        x = min(max(below.x(), area.left()), area.right() - self.width())
        y = below.y()
        if y + self.height() > area.bottom():
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 2
        self.move(x, max(y, area.top()))
        self.show()
        self.setFocus()

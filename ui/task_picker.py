"""`Task 등록` 버튼으로 뜨는 Task 등록 창

업무명(비워도 됨) / 시작 / 소요 / 종료
  - 시작은 오늘 00:00 ~ 23:45 (15분 단위), 기본값은 현재시간을 15분 단위로 내린 값
  - 소요를 바꾸면 종료를, 종료를 바꾸면 소요를 다시 계산한다.
  - 시작을 바꾸면 소요는 그대로 두고 종료 목록을 다시 만든다.
소요와 종료 목록은 같은 간격(시작 + 0:15 ~ 12:00)이라 두 콤보의 index 가 항상 같다.

Qt.Popup 이 아니라 활성화되는 Tool 창이다. Windows 에서 Popup 은 전경 창이 되지 않아
IME 가 붙지 않으므로(한글 입력 불가) 대신 다른 창이 활성화되면 스스로 닫는다.

키보드
  - Enter : 확인, Esc / 바깥 클릭 : 취소
"""

from datetime import datetime, time

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from manager import task_clock
from ui.theme import (
    ACCENT,
    FONT_FAMILY,
    POPUP_BG_COLOR,
    POPUP_FORM_STYLE,
    TEXT_MAIN,
    TEXT_SUB,
)


DURATIONS = list(
    range(task_clock.STEP_MIN, task_clock.MAX_DURATION_MIN + 1, task_clock.STEP_MIN)
)
PICKER_WIDTH = 230
ANCHOR_GAP = 4


class _TitleEdit(QLineEdit):
    """조합 중인 한글(preedit)을 기억하는 입력칸

    마지막 글자를 조합하는 중에 확인 버튼(NoFocus)을 누르면 조합이 확정되지 않아
    text() 에 빠지므로, 확인 시 preedit 을 함께 읽는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preedit = ""

    def inputMethodEvent(self, event):
        self.preedit = event.preeditString()
        super().inputMethodEvent(event)

    def full_text(self) -> str:
        text = self.text()
        if self.preedit:
            pos = self.cursorPosition()
            text = text[:pos] + self.preedit + text[pos:]
        return text


class TaskPicker(QFrame):
    picked = Signal(str, object, object)  # 업무명, 시작 datetime, 종료 datetime
    closed = Signal()  # 확인/취소와 관계없이 닫힐 때

    def __init__(self, task=None, parent=None):
        """task: 오늘 시작한 Task 가 있으면 그 값으로 채운다 (None 이면 기본값)"""
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 둥근 모서리 바깥을 투명하게 (배경은 paintEvent 가 그림)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(PICKER_WIDTH)
        self._accepted = False

        now = datetime.now().astimezone()
        self._day = now.date()
        if task is not None and task.start_at.date() == self._day:
            title, start = task.title, task.start_at
            minutes = task_clock.minutes_between(task.start_at, task.end_at)
        else:
            title, start = "", task_clock.floor_slot(now)
            minutes = task_clock.DEFAULT_DURATION_MIN

        self._build_ui()
        self.title_edit.setText(title)
        self.start_combo.setCurrentIndex(
            (start.hour * 60 + start.minute) // task_clock.STEP_MIN
        )
        duration_idx = min(
            max(minutes // task_clock.STEP_MIN - 1, 0), len(DURATIONS) - 1
        )
        self.duration_combo.setCurrentIndex(duration_idx)
        self._rebuild_end_items()

        self.start_combo.currentIndexChanged.connect(self._on_start_changed)
        self.duration_combo.currentIndexChanged.connect(self._on_duration_changed)
        self.end_combo.currentIndexChanged.connect(self._on_end_changed)

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
                border: 1px solid rgba(255,255,255,40);
                border-radius: 6px;
                padding: 4px 14px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,30); }}
            QPushButton#ok {{
                background: {ACCENT};
                color: white;
                border: 1px solid {ACCENT};
            }}
            QPushButton#ok:hover {{ background: #5b8be0; }}
            """
            + POPUP_FORM_STYLE
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QLabel("Task 등록")
        header.setStyleSheet("font-size: 13px; font-weight: bold;")
        root.addWidget(header)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # Enter 는 returnPressed 로 연결하지 않는다 - QLineEdit 가 Enter 를 부모로 넘겨
        # keyPressEvent 에서도 처리되므로 두 번 등록된다.
        self.title_edit = _TitleEdit()
        self.title_edit.setPlaceholderText("업무명 (선택)")

        self.start_combo = self._combo()
        for minutes in range(0, 24 * 60, task_clock.STEP_MIN):
            self.start_combo.addItem(f"{minutes // 60:02}:{minutes % 60:02}")

        self.duration_combo = self._combo()
        for minutes in DURATIONS:
            self.duration_combo.addItem(task_clock.format_duration(minutes))

        self.end_combo = self._combo()  # 항목은 시작에 따라 _rebuild_end_items 에서

        for row, (caption, field) in enumerate(
            (
                ("업무명", self.title_edit),
                ("시작", self.start_combo),
                ("소요", self.duration_combo),
                ("종료", self.end_combo),
            )
        ):
            lb = QLabel(caption)
            lb.setStyleSheet(f"color: {TEXT_SUB};")
            form.addWidget(lb, row, 0)
            form.addWidget(field, row, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        btn_cancel = QPushButton("취소")
        btn_ok = QPushButton("확인")
        btn_ok.setObjectName("ok")
        for btn in (btn_cancel, btn_ok):
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.close)
        btn_ok.clicked.connect(self._accept)
        buttons.addStretch(1)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        root.addLayout(buttons)

    @staticmethod
    def _combo() -> QComboBox:
        combo = QComboBox()
        combo.setFocusPolicy(Qt.NoFocus)  # 키보드는 업무명 입력칸 / 팝업이 받는다
        combo.setMaxVisibleItems(8)
        # 팝업 목록은 기본적으로 콤보 폭과 같아서 스크롤바에 밀려 잘린다
        view = combo.view()
        view.setTextElideMode(Qt.ElideNone)
        view.setMinimumWidth(view.fontMetrics().horizontalAdvance("00:00 (+1)") + 40)
        return combo

    # ==================================================
    # 시작 / 소요 / 종료 동기화
    # ==================================================
    def selected_start(self) -> datetime:
        minutes = self.start_combo.currentIndex() * task_clock.STEP_MIN
        return datetime.combine(
            self._day, time(minutes // 60, minutes % 60)
        ).astimezone()

    def selected_minutes(self) -> int:
        return DURATIONS[self.duration_combo.currentIndex()]

    def _rebuild_end_items(self):
        """시작 + 각 소요시간의 시각 목록. 자정을 넘으면 (+1)"""
        start = self.selected_start()
        self.end_combo.blockSignals(True)
        self.end_combo.clear()
        for minutes in DURATIONS:
            end = task_clock.end_from(start, minutes)
            suffix = " (+1)" if end.date() > start.date() else ""
            self.end_combo.addItem(f"{end:%H:%M}{suffix}")
        self.end_combo.setCurrentIndex(self.duration_combo.currentIndex())
        self.end_combo.blockSignals(False)

    def _on_start_changed(self, _idx: int):
        self._rebuild_end_items()

    def _on_duration_changed(self, idx: int):
        self.end_combo.blockSignals(True)
        self.end_combo.setCurrentIndex(idx)
        self.end_combo.blockSignals(False)

    def _on_end_changed(self, idx: int):
        self.duration_combo.blockSignals(True)
        self.duration_combo.setCurrentIndex(idx)
        self.duration_combo.blockSignals(False)

    # ==================================================
    # 결과
    # ==================================================
    def entered_title(self) -> str:
        """업무명 (조합 중인 한글 포함)"""
        QGuiApplication.inputMethod().commit()
        return self.title_edit.full_text().strip()

    def _accept(self):
        if self._accepted:
            return
        self._accepted = True
        start = self.selected_start()
        end = task_clock.end_from(start, self.selected_minutes())
        self.picked.emit(self.entered_title(), start, end)
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        # 바깥을 클릭해 다른 창이 활성화되면 닫는다 (Popup 과 같은 동작)
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(0, self, self._close_if_inactive)

    def _close_if_inactive(self):
        # 콤보 목록(Popup)이 열린 동안은 이 창이 비활성으로 보일 수 있다
        if not self.isActiveWindow() and QApplication.activePopupWidget() is None:
            self.close()

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
        """anchor 바로 위(공간이 없으면 아래)에 띄우고 화면 안쪽으로 맞춘다."""
        self.adjustSize()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        x = min(max(top_left.x(), area.left()), area.right() + 1 - self.width())
        y = top_left.y() - self.height() - ANCHOR_GAP
        if y < area.top():
            y = top_left.y() + anchor.height() + ANCHOR_GAP
        self.move(x, min(y, area.bottom() + 1 - self.height()))
        self.show()
        self.raise_()
        self.activateWindow()  # 전경 창이 되어야 IME(한글 입력)가 붙는다
        self.title_edit.setFocus()

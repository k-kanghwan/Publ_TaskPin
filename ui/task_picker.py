"""좌패널 [등록] / [수정] 버튼으로 뜨는 Task 등록 / 수정 창

왼쪽: 업무명(비워도 됨) / 시작 / 소요 / 종료, 오른쪽: 상세 업무(여러 줄, 비워도 됨)
  - 상세 업무는 위젯의 업무명 배지 위에 표시된다.
  - 업무명에서도 `:idea:` 같은 스니펫 트리거를 문구로 바꾼다.
  - 시작은 그날 00:00 ~ 23:45 (15분 단위). 등록 기본값은 현재시간을 15분 단위로 올린 값
    (06:36 -> 06:45 / 23:45 를 넘으면 다음 날 00:00), 수정은 그 Task 의 값
  - 소요를 바꾸면 종료를, 종료를 바꾸면 소요를 다시 계산한다.
  - 시작을 바꾸면 소요는 그대로 두고 종료 목록을 다시 만든다.
소요와 종료 목록은 같은 간격(시작 + 0:15 ~ 12:00)이라 두 콤보의 index 가 항상 같다.

Qt.Popup 이 아니라 활성화되는 Tool 창이다. Windows 에서 Popup 은 전경 창이 되지 않아
IME 가 붙지 않는다(한글 입력 불가). 다른 창을 눌러 포커스가 옮겨져도 닫히지 않고
취소 / Esc / 확인으로만 닫힌다 (적던 내용을 잃지 않게).
등록 창을 확인 없이 닫으면 canceled 로 적던 업무명 / 상세 업무를 알린다 - TaskPinApp 이 임시저장해
다음 등록 때 draft 로 다시 채운다.

키보드
  - Enter : 확인 (상세 업무 칸에서는 줄바꿈), Ctrl+Enter : 어디서든 확인
  - Tab : 업무명 -> 상세 업무, Esc : 취소
"""

from datetime import datetime, time

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from manager import task_clock
from ui import theme
from ui.text_input import PreeditLineEdit, expand_snippet_later


DURATIONS = list(
    range(task_clock.STEP_MIN, task_clock.MAX_DURATION_MIN + 1, task_clock.STEP_MIN)
)
PICKER_WIDTH = 470
FORM_WIDTH = 210  # 왼쪽 업무명 / 시간 칸 (나머지는 상세 업무)
ANCHOR_GAP = 4


class _TitleEdit(PreeditLineEdit):
    """업무명 칸. 스니펫을 치환한다.

    마지막 글자를 조합하는 중에 확인 버튼(NoFocus)을 누르면 조합이 확정되지 않아
    text() 에 빠지므로, 확인 시 full_text() 로 preedit 을 함께 읽는다."""

    def __init__(self, snippets_provider, parent=None):
        super().__init__(parent)
        self._snippets_provider = snippets_provider
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, _text: str):
        if not self.preedit:
            expand_snippet_later(self, self._snippets_provider)


class _DetailEdit(QPlainTextEdit):
    """상세 업무 칸. 조합 중인 한글(preedit)을 기억하고, Ctrl+Enter / Esc 는 등록 창으로 넘긴다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preedit = ""
        self.setTabChangesFocus(True)

    def inputMethodEvent(self, event):
        self.preedit = event.preeditString()
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        ctrl_enter = event.key() in (Qt.Key_Return, Qt.Key_Enter) and (
            event.modifiers() & Qt.ControlModifier
        )
        if ctrl_enter or event.key() == Qt.Key_Escape:
            event.ignore()  # 부모(TaskPicker.keyPressEvent)가 확인 / 취소
            return
        super().keyPressEvent(event)

    def full_text(self) -> str:
        text = self.toPlainText()
        if self.preedit:
            # QTextCursor 위치는 UTF-16 단위
            units = text.encode("utf-16-le")[: self.textCursor().position() * 2]
            pos = len(units.decode("utf-16-le", "ignore"))
            text = text[:pos] + self.preedit + text[pos:]
        return text


class TaskPicker(QFrame):
    picked = Signal(
        str, str, object, object
    )  # 업무명, 상세, 시작 datetime, 종료 datetime
    closed = Signal()  # 확인/취소와 관계없이 닫힐 때
    canceled = Signal(str, str)  # 확인 없이 닫힘 - 적던 업무명, 상세 업무 (임시저장용)

    def __init__(self, task, snippets_provider, parent=None, draft=("", "")):
        """task: None 이면 새 등록(기본값), 있으면 그 Task 를 수정 (값을 채우고 제목이 "Task 수정")
        snippets_provider: () -> {트리거: 문구} (업무명 스니펫 치환)
        draft: 새 등록일 때 미리 채울 (업무명, 상세 업무) - 지난번에 취소한 내용"""
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 둥근 모서리 바깥을 투명하게 (배경은 paintEvent 가 그림)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(PICKER_WIDTH)
        self._accepted = False
        self._snippets_provider = snippets_provider
        self._theme = theme.current()
        self._editing = task is not None

        if self._editing:
            title, detail, start = task.title, task.detail, task.start_at
            minutes = task_clock.minutes_between(task.start_at, task.end_at)
        else:
            title, detail = draft
            start = task_clock.ceil_slot(datetime.now().astimezone())
            minutes = task_clock.DEFAULT_DURATION_MIN
        self._day = start.date()

        self._build_ui()
        self.title_edit.setText(title)
        self.detail_edit.setPlainText(detail)
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
        t = self._theme
        self.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
                font-size: 12px;
            }}
            QPushButton {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
                font-size: 12px;
                border: 1px solid {t.overlay(40)};
                border-radius: 6px;
                padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {t.overlay(30)}; }}
            QPushButton#ok {{
                background: {t.accent};
                color: {t.on_accent};
                border: 1px solid {t.accent};
            }}
            QPushButton#ok:hover {{ background: {t.accent_hover}; }}
            QPlainTextEdit {{
                background: {t.overlay(18)};
                color: {t.text_main};
                font-family: {t.font_family};
                font-size: 12px;
                border: 1px solid {t.overlay(40)};
                border-radius: 6px;
                padding: 2px 4px;
                selection-background-color: {t.accent};
                selection-color: {t.on_accent};
            }}
            QPlainTextEdit:focus {{ border: 1px solid {t.overlay(90)}; }}
            """
            + theme.popup_form_style(t)
            + theme.menu_style(t)  # 입력칸 우클릭 메뉴
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QLabel("Task 수정" if self._editing else "Task 등록")
        header.setStyleSheet("font-size: 13px; font-weight: bold;")
        root.addWidget(header)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # Enter 는 returnPressed 로 연결하지 않는다 - QLineEdit 가 Enter 를 부모로 넘겨
        # keyPressEvent 에서도 처리되므로 두 번 등록된다.
        self.title_edit = _TitleEdit(self._snippets_provider)
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
            lb.setStyleSheet(f"color: {t.text_sub};")
            form.addWidget(lb, row, 0)
            form.addWidget(field, row, 1)
        form.setColumnStretch(1, 1)
        form_box = QWidget()
        form_box.setFixedWidth(FORM_WIDTH)
        form_box.setLayout(form)
        form.setContentsMargins(0, 0, 0, 0)

        # ---- 오른쪽: 상세 업무 (왼쪽 폼 높이에 맞춤) ----
        self.detail_edit = _DetailEdit()
        self.detail_edit.setPlaceholderText("상세 업무 (선택) · 업무명 배지 위에 표시")
        # 기본 크기 힌트(약 190px)대로 창이 길어지지 않고 왼쪽 폼 높이를 따르도록
        self.detail_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(form_box, 0, Qt.AlignTop)
        body.addWidget(self.detail_edit, 1)
        root.addLayout(body)

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

    def entered_detail(self) -> str:
        """상세 업무 (조합 중인 한글 포함)"""
        QGuiApplication.inputMethod().commit()
        return self.detail_edit.full_text().strip()

    def _accept(self):
        if self._accepted:
            return
        self._accepted = True
        start = self.selected_start()
        end = task_clock.end_from(start, self.selected_minutes())
        self.picked.emit(self.entered_title(), self.entered_detail(), start, end)
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    @property
    def editing(self) -> bool:
        """진행 중인 Task 를 고치는 창인지 (아니면 새 등록)"""
        return self._editing

    def closeEvent(self, event):
        if not self._accepted:
            self.canceled.emit(self.entered_title(), self.entered_detail())
        self.closed.emit()
        super().closeEvent(event)

    def paintEvent(self, event):
        # 반투명 최상위 창은 스타일시트 배경이 그려지지 않으므로 직접 그린다
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.fillPath(path, QColor(self._theme.popup_bg))
        painter.setPen(QColor(self._theme.menu_border))
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

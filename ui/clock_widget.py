"""바탕화면 Task 시간 위젯 (PySide6)

Priv_dtcal/dtcal_poc.py 에서 검증된 기법을 이식:
  - Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint
  - WA_TranslucentBackground + paintEvent 로 둥근 반투명 배경 직접 그리기
  - globalPosition() 오프셋 방식 드래그

이 위젯은 "멍청한 뷰"다. Task 저장 / 시간 계산은 전부 TaskPinApp 이 담당하고,
위젯은 시그널로 요청만 올려보낸 뒤 apply_task() / set_clock() 으로 값을 받아 그린다.
(사용자 이름 / TODO / 위젯 설정은 위젯이 직접 저장한다)

단축키(설정창 Keyboard Shortcuts 탭)는 위젯 창이 활성일 때만 동작한다. E/C/A 같은 글자 키와 Enter 는
입력칸이 먼저 가져가므로(ShortcutOverride) 할 일이나 이름을 입력하는 중에는 글자로 들어간다.
투명도는 설정창 Appearance 의 슬라이더로 정한다 (config opacity).
Task 등록 / 수정 창이 떠 있는 동안에는 투명한 막(_InputBlocker)이 위젯을 덮어 끌어 옮기기만 된다.
등록 / 수정 창과 내보내기 파일 창이 떠 있는 동안은 "항상 위에 보이기" 설정과 관계없이 위에 둔다 (hold_on_top).
리마인더 알림 팝업은 주 모니터 우측 상단부터 쌓고, 하나가 닫히면 아래 팝업이 위로 미끄러져 올라온다.
팝업의 버튼이 아닌 곳을 누르면 위젯을 띄워 그 할 일로 가서 깜빡인다 (show_todo).
"""

import os
from datetime import datetime

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    QStandardPaths,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPainterPath,
    QShortcut,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from manager import (
    os_win,
    snippets,
    todo_export,
    todo_import,
    todo_pages,
    todo_store,
    widget_config,
)
from ui import menus, painted, theme
from ui.confirm_dialog import ConfirmDialog
from ui.painted import EditableLabel
from ui.reminder_popup import ReminderPopup
from ui.task_history import TaskHistory
from ui.text_input import LineEdit
from ui.theme import CORNER_RADIUS, px
from ui.todo_panel import TodoPanel

# ========= ========= 테마 ========= =========
# 최소 크기 - 세로 모드: 폭 280 / 높이 324(글자 배율로 더 커질 수 있음), 가로 모드: 폭 540(좌 시간 280 + 우 TODO)
# 최대 크기는 두 모드 모두 연결된 모니터 중 가장 작은 작업 영역의 80% (widget_config.screen_limit - _max_size)
WIDGET_WIDTH = 280
WIDGET_MIN_HEIGHT = 324
WIDGET_MIN_WIDTH_HORIZONTAL = 540
RESIZE_MARGIN = 6  # 하단/우측 크기 조절 영역(px) - root 마진(14/16px) 안쪽
TASK_BUTTON_REGISTER = "등록"  # [등록/해제] 버튼: Task 가 없을 때
TASK_BUTTON_RELEASE = "해제"  # [등록/해제] 버튼: Task 가 진행 중일 때
SCREEN_MARGIN = 24
CONTENT_MARGIN_H = 16  # root 좌우 마진
CONTENT_MARGIN_V = 14  # root 상하 마진
COLUMN_SPACING = 12  # 가로 모드 좌/우 칼럼 사이 간격
# 좌측 칼럼 폭: 가로 모드는 고정, 세로 모드는 위젯 폭을 따라 늘어난다
LEFT_COL_WIDTH = WIDGET_WIDTH - CONTENT_MARGIN_H * 2
QWIDGETSIZE_MAX = 16777215

ORIENTATION_VERTICAL = "vertical"
ORIENTATION_HORIZONTAL = "horizontal"

FRONT_CHECK_MS = 300  # 앞으로 꺼낸 동안 다른 앱이 활성화됐는지 확인하는 주기
REMINDER_CHECK_MS = 20 * 1000  # 리마인더 확인 주기
REMINDER_STARTUP_DELAY_MS = 3 * 1000  # 앱이 꺼져있던 동안 지난 알림을 시작 직후 확인
POPUP_GAP = 8
POPUP_SLIDE_MS = 180  # 알림이 닫혀 아래 알림이 위로 올라오는 시간

TASK_DOT_COLOR = "#4caf50"  # Task 시간이 등록되어 있을 때 헤더의 점
USER_NAME_MAX_LEN = 20
# 헤더 오른쪽 프로필 칩 (프로필이 둘 이상일 때 - set_profile). 긴 이름은 이 폭(배율 전)에서 말줄임
PROFILE_CHIP_MAX_WIDTH = 110
PROFILE_CHIP_RADIUS = 8
TASK_BADGE_H_SPACE = 2 * 8 + 2 * 1  # 좌우 padding + border (말줄임 폭 계산용)
# 업무명 배지 위 상세업무 - 세로 모드 최대 줄 수
# (가로 모드는 업무 이력이 켜져 있으면 cfg task_detail_lines, 꺼져 있으면 내용만큼)
TASK_DETAIL_MAX_LINES = 3
# 업무 이력 / 상세업무 카드 (업무 이력 = 중립 덧칠색 - ui/task_history, 상세업무 = 강조색 옅게)
CARD_RADIUS = 6
DETAIL_CARD_BG_ALPHA = 24  # 상세업무 카드 배경 = 강조색 이 알파 (업무명 배지 40 보다 옅게)
DETAIL_CARD_MARGINS = (8, 6, 8, 6)  # 카드 안쪽 여백 (왼, 위, 오른, 아래)
SPLIT_HANDLE_H = 9  # 두 카드 사이 끄는 선의 높이 (선은 가운데 1px)
SPLIT_TIP = "끌어서 상세 업무 높이 조절 · 더블클릭: 기본(3줄)"
FIXED_EDIT_KEY = "F2"  # 할 일 수정 고정 키 (설정 단축키 todo_edit 와 함께 - 기본 Enter)
# 되돌리기 / 다시 실행 고정 키 (설정 단축키 todo_undo / todo_redo 와 함께)
FIXED_UNDO_KEYS = ("Ctrl+Z",)
FIXED_REDO_KEYS = ("Ctrl+Y", "Ctrl+Shift+Z")
# ========= ========= ========= ========= =========


def _wrap_lines(text: str, font, width: int) -> list:
    """text 를 width 에 맞춰 줄바꿈한 줄 목록"""
    lines = []
    for para in text.splitlines():
        units = para.encode("utf-16-le")  # QTextLine 위치는 UTF-16 단위
        layout = QTextLayout(para, font)
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start, length = line.textStart() * 2, line.textLength() * 2
            lines.append(units[start : start + length].decode("utf-16-le").rstrip())
        layout.endLayout()
        if not para:
            lines.append("")
    return lines


def _elide_lines(text: str, font, width: int, max_lines: int):
    """text 를 width 에 맞춰 줄바꿈하고 max_lines 를 넘으면 마지막 줄을 "…" 로 줄인다.
    Returns (표시할 문자열, 줄였는지)"""
    lines = _wrap_lines(text, font, width)
    if len(lines) <= max_lines:
        return "\n".join(lines), False
    fm = QFontMetrics(font)
    last = lines[max_lines - 1]
    while last and fm.horizontalAdvance(last + "…") > width:
        last = last[:-1]
    return "\n".join(lines[: max_lines - 1] + [last.rstrip() + "…"]), True


class _DetailLabel(QLabel):
    """업무명 배지 위 상세업무. 받은 높이에 들어가는 줄 수만큼 보여주고, 넘치면 마지막 줄을
    "…" 로 줄인다(전체는 툴팁). max_lines 를 주면(세로 모드) 그 줄 수까지만 자리를 요청하고,
    주지 않으면(가로 모드) 좌패널의 남는 높이를 모두 받는다 (ClockWidget._apply_orientation)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.PlainText)
        self._full = ""
        self._max_lines = None

    def set_full_text(self, text: str):
        self._full = text
        self.updateGeometry()
        self._refit()

    def set_max_lines(self, max_lines):
        self._max_lines = max_lines
        self.updateGeometry()
        self._refit()

    def _line_height(self) -> int:
        self.ensurePolished()  # 스타일시트 글꼴로 재기 위해
        return self.fontMetrics().lineSpacing()

    def sizeHint(self) -> QSize:
        # 폭은 좌측 칼럼을 따르므로 0 (긴 줄이 칼럼을 넓히지 않게)
        lines = len(_wrap_lines(self._full, self.font(), max(1, self.width())))
        if self._max_lines:
            lines = min(lines, self._max_lines)
        return QSize(0, max(1, lines) * self._line_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._line_height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()  # 폭이 바뀌면 필요한 줄 수도 바뀐다
        self._refit()

    def _refit(self):
        fits = max(1, self.height() // self._line_height())
        if self._max_lines:
            fits = min(fits, self._max_lines)
        shown, elided = _elide_lines(
            self._full, self.font(), max(1, self.width()), fits
        )
        self.setText(shown)
        self.setToolTip(self._full if elided else "")


class _DetailCard(QWidget):
    """상세업무 카드: _DetailLabel 을 안쪽 여백으로 감싸고 강조색 옅은 배경(apply_appearance)을 깐다.
    lines 를 정하면(가로 모드 + 업무 이력 켬) 내용과 관계없이 그 줄 수만큼의 높이를 바란다 - 공간이 모자라면
    최소 한 줄까지 줄어든다. None 이면 라벨(내용 줄 수, 세로 모드는 3줄까지)을 따른다.
    바라는 높이보다 커지지 않는다(Maximum) - 남는 높이는 업무 이력 / 여백이 받는다."""

    def __init__(self, label: _DetailLabel, parent=None):
        super().__init__(parent)
        self.label = label
        self.lines = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*DETAIL_CARD_MARGINS)
        layout.addWidget(label)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def set_lines(self, lines):
        if lines != self.lines:
            self.lines = lines
            self.updateGeometry()

    def margins_v(self) -> int:
        margins = self.layout().contentsMargins()
        return margins.top() + margins.bottom()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if self.lines is not None:
            hint.setHeight(self.lines * self.label._line_height() + self.margins_v())
        return hint


class _SplitHandle(QWidget):
    """업무 이력 카드와 상세업무 카드 사이 선 - 위아래로 끌어 상세업무 카드 높이(줄 단위)를 정한다.
    줄 수 계산 / 저장은 ClockWidget(_on_split_*)이 한다. 위치 / 크기 잠금이면 끌지 않고 선만 보인다
    (누름은 위젯으로 올라가 다른 곳처럼 처리된다)."""

    drag_started = Signal()
    dragged = Signal(float)  # 누른 곳에서 커서가 움직인 거리 (아래로 +)
    drag_finished = Signal()
    reset_requested = Signal()  # 더블클릭: 기본 줄 수

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(SPLIT_HANDLE_H)
        self.setAttribute(Qt.WA_Hover, True)
        self._press_y = None
        self.set_enabled(True)

    def set_enabled(self, enabled: bool):
        self.setCursor(Qt.SizeVerCursor if enabled else Qt.ArrowCursor)
        self.setToolTip(SPLIT_TIP if enabled else "")
        self.setEnabled(enabled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_y = event.globalPosition().y()
            self.drag_started.emit()
            self.update()
        # 누름은 여기서 끝 (위젯 창이 끌려 옮겨지지 않게)

    def mouseMoveEvent(self, event):
        if self._press_y is not None and (event.buttons() & Qt.LeftButton):
            self.dragged.emit(event.globalPosition().y() - self._press_y)

    def mouseReleaseEvent(self, event):
        if self._press_y is not None and event.button() == Qt.LeftButton:
            self._press_y = None
            self.drag_finished.emit()
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reset_requested.emit()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        t = theme.current()
        active = self.isEnabled() and (self.underMouse() or self._press_y is not None)
        painter = QPainter(self)
        y = self.height() // 2
        painter.fillRect(
            0, y, self.width(), 1, QColor(t.accent) if active else t.overlay_color(40)
        )
        if active:  # 끌 수 있다는 손잡이 (크기 조절 핸들 _ResizeGrip 과 같은 모양)
            painter.setRenderHint(QPainter.Antialiasing)
            bar = QRectF(self.width() / 2 - 16, y - 1, 32, 3)
            path = QPainterPath()
            path.addRoundedRect(bar, 1.5, 1.5)
            painter.fillPath(path, QColor(t.accent))


class _ResizeGrip(QWidget):
    """위젯 가장자리의 크기 조절 핸들 (하단: 높이 / 우측: 폭 - 두 모드 모두)

    부모 위젯의 mouseMoveEvent 로 커서를 바꾸면 자식 위젯 위에서 커서가
    원복되지 않으므로, 커서를 자체적으로 갖는 얇은 자식 위젯으로 분리한다.
    """

    def __init__(self, window: "ClockWidget", vertical: bool):
        super().__init__(window)
        self._window = window
        self._vertical = vertical  # True: 높이 조절 / False: 폭 조절
        self._origin = None  # (누른 지점의 global 좌표, 그때의 크기)
        self._hover = False

    def set_enabled(self, enabled: bool):
        resize_cursor = Qt.SizeVerCursor if self._vertical else Qt.SizeHorCursor
        self.setCursor(resize_cursor if enabled else Qt.ArrowCursor)
        self.setEnabled(enabled)

    def _pos(self, event) -> float:
        point = event.globalPosition()
        return point.y() if self._vertical else point.x()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            size = self._window.height() if self._vertical else self._window.width()
            self._origin = (self._pos(event), size)

    def mouseMoveEvent(self, event):
        if self._origin is not None and (event.buttons() & Qt.LeftButton):
            start, start_size = self._origin
            size = round(start_size + self._pos(event) - start)
            # min/max 범위는 Qt 가 알아서 clamp 한다
            if self._vertical:
                self._window.resize(self._window.width(), size)
            else:
                self._window.resize(size, self._window.height())

    def mouseReleaseEvent(self, event):
        if self._origin is not None:
            self._origin = None
            self._window.save_size()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        if not (self._hover and self.isEnabled()):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._vertical:
            bar = QRectF(self.width() / 2 - 16, self.height() / 2 - 1.5, 32, 3)
        else:
            bar = QRectF(self.width() / 2 - 1.5, self.height() / 2 - 16, 3, 32)
        path = QPainterPath()
        path.addRoundedRect(bar, 1.5, 1.5)
        painter.fillPath(path, theme.current().overlay_color(90))


class _NameEdit(LineEdit):
    """사용자 이름 편집칸 (Enter / 포커스 이동: 저장, Esc: 취소)"""

    escaped = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


class _InputBlocker(QWidget):
    """Task 등록 / 수정 창이 떠 있는 동안 위젯 전체를 덮는 투명한 막.
    누르고 끌면 위젯 창 이동만 된다(누름 / 이동 / 뗌을 부모 ClockWidget 으로 넘김).
    항목 클릭 / 우클릭 / 휠 / 키 입력 / 창 단축키는 막는다. 누름을 떼면 released 로 알려 등록 창을 다시 앞으로."""

    released = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        # 누르면 포커스를 가져와 키 입력이 아래 입력칸 / 목록으로 가지 않게 한다
        self.setFocusPolicy(Qt.ClickFocus)
        self.hide()

    def event(self, event):
        kind = event.type()
        if kind == QEvent.ShortcutOverride:
            event.accept()  # 창 단축키(E / C / A ...) 대신 이 막이 받아서 버린다
            return True
        if kind in (QEvent.KeyPress, QEvent.KeyRelease):
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        event.ignore()  # 부모(ClockWidget)가 창 이동을 시작한다

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.released.emit()
        event.ignore()  # 부모가 옮긴 위치를 저장한다

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()  # 부모로 올라가 좌패널 메뉴가 뜨지 않게


class ClockWidget(QWidget):
    """바탕화면에 상주하는 Task 시간 + TODO 위젯"""

    task_register_requested = Signal()  # [등록/해제] - Task 가 없을 때
    task_release_requested = Signal()  # [등록/해제] - Task 가 진행 중일 때
    task_edit_requested = Signal()  # [수정]
    task_clear_requested = Signal()  # [완료]
    settings_requested = Signal()
    quit_requested = Signal()
    visibility_changed = Signal(bool)
    reminder_due = Signal(str, str)  # item id, 본문
    # Task 등록 / 수정 창이 떠 있는 동안 위젯을 눌렀다 뗌 - TaskPinApp 이 그 창을 다시 앞으로 올린다
    blocked_clicked = Signal()

    def __init__(self, cfg: dict):
        super().__init__()

        self._cfg = cfg
        # 설정과 관계없이 잠깐 위에 붙잡아 두는 이유들 ("picker" 등록 창 / "export" 내보내기 창 - hold_on_top)
        self._top_holds = set()
        self._locked = bool(cfg.get("locked", False))
        self._drag_offset = None
        self._popups = []
        self._shortcuts = []
        self._separators = []  # 테마가 바뀌면 다시 칠할 구분선
        self._task_title = ""  # 업무명 배지 원문 (말줄임 전)
        # 지금 프로필 (헤더 칩 / 우클릭 "프로필" 메뉴 제목 - set_profile)
        self._profile_name = ""
        # (QMenu) -> None: 프로필 메뉴를 채운다 (TaskPinApp)
        self._profile_menu_filler = None
        self._task_detail = ""  # 상세업무 원문 (말줄임 전)
        # 가로 / 세로 모드 - _build_ui 안의 apply_task(None) → _apply_split 이 읽으므로 먼저 둔다
        # (실제 모드는 아래 _apply_orientation 이 정한다)
        self._orientation = None
        # 트레이 클릭으로 다른 앱보다 위에 꺼내 둔 상태
        self._front = False
        self._front_baseline = (
            None  # 꺼낼 때의 전경 창 (트레이 클릭 직후라 보통 작업표시줄)
        )
        self._front_timer = QTimer(self)
        self._front_timer.setInterval(FRONT_CHECK_MS)
        self._front_timer.timeout.connect(self._check_front)

        # 1) 프레임리스 + 작업표시줄/Alt-Tab 제외(Tool) + 항상 맨 아래(또는 맨 위)
        self._apply_window_flags()
        # 2) 반투명 배경 (paintEvent 에서 직접 그림)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 표시(시작/위젯 보이기)만으로 활성화되어 앞으로 튀어나오지 않게 - 클릭했을 때만 앞으로
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # 투명도는 오직 설정창의 투명도 슬라이더(cfg opacity)로만 정한다 (배경색 자체는 불투명)
        # - apply_appearance / apply_opacity 의 _apply_opacity

        self._build_ui()
        self._grip_v = _ResizeGrip(self, vertical=True)  # 하단: 높이
        self._grip_h = _ResizeGrip(self, vertical=False)  # 우측: 폭 (가로 모드만)
        self._set_grips_enabled(not self._locked)
        # Task 등록 / 수정 창이 떠 있는 동안 위젯을 덮는 막 (set_input_blocked)
        self._blocker = _InputBlocker(self)
        self._blocker.released.connect(self.blocked_clicked.emit)
        # 3) 크기 범위 / 조절 방향은 모드별로 (세로: 높이만, 가로: 폭과 높이)
        self._orientation = None
        self._apply_orientation(self._cfg_orientation())
        self._watch_screens()
        self.apply_appearance()
        self._restore_position()
        self.apply_shortcuts(widget_config.shortcuts(self._cfg))

        # 4) 리마인더 (위젯이 숨겨져 있어도 계속 확인)
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(REMINDER_CHECK_MS)
        QTimer.singleShot(REMINDER_STARTUP_DELAY_MS, self.check_reminders)

    @staticmethod
    def _max_size() -> tuple:
        """최대 크기 (폭, 높이): 연결된 모니터 중 가장 작은 작업 영역의 80% (모니터를 모르면 제한 없음)"""
        limit = widget_config.screen_limit(
            (geo.width(), geo.height())
            for geo in (
                screen.availableGeometry() for screen in QGuiApplication.screens()
            )
        )
        return limit or (QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

    def _limits(self) -> tuple:
        """지금 모드의 (최소 폭, 최소 높이, 최대 폭, 최대 높이). 최대는 최소보다 작아지지 않는다."""
        min_width = (
            WIDGET_MIN_WIDTH_HORIZONTAL
            if self._orientation == ORIENTATION_HORIZONTAL
            else WIDGET_WIDTH
        )
        min_height = self._min_height()
        max_width, max_height = self._max_size()
        return (
            min_width,
            min_height,
            max(min_width, max_width),
            max(min_height, max_height),
        )

    def _cfg_size(self, key: str, default: int, low: int, high: int) -> int:
        """설정에 저장된 크기 (없거나 깨졌으면 default) 를 low ~ high 로"""
        try:
            value = int(self._cfg.get(key) or default)
        except (TypeError, ValueError):
            value = default
        return min(high, max(low, value))

    def _cfg_orientation(self) -> str:
        value = self._cfg.get("orientation")
        if value in (ORIENTATION_VERTICAL, ORIENTATION_HORIZONTAL):
            return value
        return ORIENTATION_VERTICAL

    def _cfg_on_top(self) -> bool:
        """설정 "항상 위에 보이기" (좌패널 메뉴의 체크)"""
        return bool(self._cfg.get("always_on_top", False))

    def _on_top(self) -> bool:
        """실제로 위에 둘지: 설정이 켜졌거나, 등록 창 / 내보내기 창 때문에 잠깐 붙잡아 둔 동안 (hold_on_top)"""
        return self._cfg_on_top() or bool(self._top_holds)

    def hold_on_top(self, key: str, on: bool):
        """등록 / 수정 창, 내보내기 파일 창이 떠 있는 동안은 설정과 관계없이 위젯을 위에 둔다 (key 별로 붙잡음).
        다른 앱을 눌러도 위젯과 그 창이 뒤로 숨지 않는다. 다 풀리면 설정대로 돌아간다
        (이 앱의 창을 쓰는 중이면 바로 바탕화면으로 내리지 않고 앞으로 꺼낸 상태 - _apply_stay_mode)."""
        before = self._on_top()
        if on:
            self._top_holds.add(key)
        else:
            self._top_holds.discard(key)
        if self._on_top() != before:
            self._apply_stay_mode()

    def _apply_window_flags(self):
        stay_hint = (
            Qt.WindowStaysOnTopHint if self._on_top() else Qt.WindowStaysOnBottomHint
        )
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | stay_hint)

    def _apply_z_order(self):
        """Qt 플래그만으로 반영되지 않는 항상 위/아래를 Win32 로 보정"""
        if not self.isVisible() or self._front:
            return
        hwnd = int(self.winId())
        if self._on_top():
            os_win.set_z_order(hwnd, os_win.HWND_TOPMOST)
        else:
            os_win.set_z_order(hwnd, os_win.HWND_NOTOPMOST)
            os_win.set_z_order(hwnd, os_win.HWND_BOTTOM)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_z_order()

    # ==================================================
    # 트레이 클릭 / 위젯 클릭: 다른 앱보다 위로 꺼내기
    # ==================================================
    def changeEvent(self, event):
        super().changeEvent(event)
        # 위젯을 클릭해 활성화되면 트레이 클릭과 같이 앞으로 (클릭 처리가 끝난 뒤에 플래그를 바꾼다)
        if (
            event.type() == QEvent.ActivationChange
            and self.isActiveWindow()
            and not self._front
        ):
            QTimer.singleShot(0, self._on_activated)

    def _on_activated(self):
        # 그 사이 다른 앱으로 넘어갔으면 활성화를 다시 빼앗지 않는다
        if self.isActiveWindow() and not self._front:
            self.bring_to_front()

    def bring_to_front(self):
        """다른 앱보다 위로 올리고 활성화한다.
        다른 앱(바탕화면 포함)이 활성화되면 _check_front 가 다시 바탕화면 층으로 돌려보낸다."""
        if not self.isVisible():
            return
        if not self._on_top():
            self._front = True
            self._set_bottom_hint(False)
            # 비활성 앱이라 활성화가 거부돼도 z-order 는 맨 위(최상위 창 아래)로 올라가도록
            hwnd = int(self.winId())
            os_win.set_z_order(hwnd, os_win.HWND_TOPMOST)
            os_win.set_z_order(hwnd, os_win.HWND_NOTOPMOST)
            self._front_baseline = os_win.foreground_window()
            self._front_timer.start()
        self.raise_()
        self.activateWindow()

    def _check_front(self):
        hwnd = os_win.foreground_window()
        if not self.isVisible():
            self._send_to_back()
        elif os_win.is_own_window(hwnd):
            # 한 번 활성화되고 나면, 이후 어떤 다른 창으로 넘어가도 복귀
            self._front_baseline = None
        elif hwnd != self._front_baseline:
            self._send_to_back()

    def _send_to_back(self):
        self._front_timer.stop()
        self._front = False
        self._set_bottom_hint(True)
        self._apply_z_order()

    def _set_bottom_hint(self, on: bool):
        """WindowStaysOnBottomHint 가 켜져 있으면 Qt 가 모든 z-order 변경을 맨 아래로 되돌리므로
        꺼낼 때는 힌트를 뺀다. setWindowFlags 는 창을 숨겼다 다시 띄워(깜빡임)
        QWidget 쪽 플래그와 네이티브 창 플래그만 맞춰서 바꾼다."""
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowStaysOnBottomHint
        else:
            flags &= ~Qt.WindowStaysOnBottomHint
        self.overrideWindowFlags(flags)
        self.windowHandle().setFlags(flags)
        # 네이티브 스타일을 다시 적용하면 반투명(레이어드) 창의 그림이 비워지므로 전체를 다시 그린다
        self.repaint()

    # ==================================================
    # UI 구성
    # ==================================================
    def _build_ui(self):
        """위젯 배치만 한다. 색 / 글자 크기는 apply_appearance 에서 입힌다."""
        root = QHBoxLayout(self)
        root.setContentsMargins(
            CONTENT_MARGIN_H, CONTENT_MARGIN_V, CONTENT_MARGIN_H, CONTENT_MARGIN_V
        )
        root.setSpacing(COLUMN_SPACING)

        # ---- 좌: Task 시간 정보 (세로 모드에서는 info 와 controls 사이에 TODO 가 들어감) ----
        # 세로 모드 폭에서 마진을 뺀 값으로 고정 - 가로 모드에서도 TODO 추가 전 위젯과 같은 폭
        self._left_col = QWidget()
        self._left_col.setFixedWidth(
            LEFT_COL_WIDTH
        )  # 세로 모드에서는 _apply_orientation 이 풀어 준다
        self._left_layout = QVBoxLayout(self._left_col)
        self._left_layout.setContentsMargins(0, 0, 0, 0)
        self._left_layout.setSpacing(6)

        info_box = QWidget()
        info = QVBoxLayout(info_box)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(6)

        # ---- 헤더: Task 등록 여부 점 + 사용자 이름 ----
        header = QHBoxLayout()
        header.setSpacing(8)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)

        # 이름은 위젯에서 유일하게 더블클릭으로 편집하는 곳 - 같은 자리에 편집칸을 띄운다
        self.name_label = EditableLabel()
        self.name_label.setToolTip("더블클릭하여 이름 수정")
        self.name_label.installEventFilter(self)

        self.name_edit = _NameEdit()
        self.name_edit.setMaxLength(USER_NAME_MAX_LEN)
        self.name_edit.setPlaceholderText("이름")
        self.name_edit.hide()
        self.name_edit.returnPressed.connect(self._commit_name_edit)
        self.name_edit.focus_lost.connect(self._commit_name_edit)
        self.name_edit.escaped.connect(self._finish_name_edit)

        # 프로필이 둘 이상이면 이름 오른쪽에 지금 프로필 - 누르면 프로필 메뉴 (set_profile)
        self.profile_button = QPushButton()
        self.profile_button.setObjectName("profile")
        self.profile_button.setCursor(Qt.PointingHandCursor)
        self.profile_button.setFocusPolicy(Qt.NoFocus)
        self.profile_button.clicked.connect(self._show_profile_menu)
        self.profile_button.hide()

        header.addWidget(self.status_dot)
        # 테두리가 글자만 감싸도록 남는 폭은 늘리지 않는다 (편집칸은 남는 폭을 모두 받음)
        header.addWidget(self.name_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
        header.addWidget(self.name_edit, 1)
        header.addWidget(self.profile_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        info.addLayout(header)

        # ---- 현재시간 ----
        self.now_label = QLabel("현재시간  --:--:--")
        info.addWidget(self.now_label)

        info.addWidget(self._separator())

        # ---- 남은시간 (주력 정보) ----
        self.remaining_label = QLabel("--:--")
        self.remaining_label.setAlignment(Qt.AlignCenter)
        info.addWidget(self.remaining_label)

        self.remaining_caption = QLabel(
            "남은시간"
        )  # 고정 라벨 - 초과는 색과 + 로만 표시
        self.remaining_caption.setAlignment(Qt.AlignCenter)
        info.addWidget(self.remaining_caption)

        info.addWidget(self._separator())

        # ---- Task 시작 / 종료 ----
        times = QHBoxLayout()
        times.setSpacing(8)
        self.in_label = QLabel("시작 --:--")
        self.out_label = QLabel("종료 --:--")
        times.addWidget(self.in_label)
        times.addStretch(1)
        times.addWidget(self.out_label)
        info.addLayout(times)

        info.addWidget(self._separator())

        controls_box = QWidget()
        controls = QVBoxLayout(controls_box)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        # ---- 업무 이력 / 상세업무: 시작/종료와 업무명 배지 사이 (_split_box, 배치는 _apply_split) ----
        # [업무 이력 카드(가로 모드만), 여백, 끄는 선, 상세업무 카드(비어 있으면 숨김)]
        self.task_history = TaskHistory()
        self.task_history.hide()
        self._history_on = False  # 설정에서 켰는지 (set_task_history)
        self.task_detail_label = _DetailLabel()
        self.task_detail_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._detail_card = _DetailCard(self.task_detail_label)
        self._detail_card.hide()
        self._split_handle = _SplitHandle()
        self._split_handle.hide()
        self._split_handle.drag_started.connect(self._on_split_start)
        self._split_handle.dragged.connect(self._on_split_drag)
        self._split_handle.drag_finished.connect(self._on_split_end)
        self._split_handle.reset_requested.connect(self._on_split_reset)
        self._split_origin = None  # 끄는 중: (누를 때 카드 높이, 줄 높이, 카드가 커질 수 있는 높이)
        self._split_box = QWidget()
        split = QVBoxLayout(self._split_box)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)
        split.addWidget(self.task_history, 1)  # 업무 이력이 보이면 남는 높이를 받는다
        split.addStretch(0)  # 업무 이력이 없을 때 남는 높이 (가로 모드: controls 를 바닥에)
        split.addWidget(self._split_handle)
        split.addWidget(self._detail_card)

        # ---- 업무명 배지: 등록한 Task 강조 (비어 있으면 숨김 / 클릭 없음) ----
        self.task_title_label = QLabel()
        self.task_title_label.setTextFormat(Qt.PlainText)
        self.task_title_label.setAlignment(Qt.AlignCenter)
        self.task_title_label.hide()
        controls.addWidget(self.task_title_label)

        # ---- [등록/해제] [수정] [완료] 버튼 ----
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_task = QPushButton(TASK_BUTTON_REGISTER)
        self.btn_task_edit = QPushButton("수정")
        self.btn_task_edit.setToolTip("진행 중인 Task 수정")
        self.btn_task_clear = QPushButton("완료")
        self.btn_task_clear.setToolTip("진행 중인 Task 완료")
        for btn in (self.btn_task, self.btn_task_edit, self.btn_task_clear):
            btn.setCursor(Qt.PointingHandCursor)
            # 클릭으로 포커스를 받으면 글자 둘레에 점선 포커스 표시가 생긴다 (단축키는 창 단위라 상관없음)
            btn.setFocusPolicy(Qt.NoFocus)
            buttons.addWidget(btn)
        self.btn_task.clicked.connect(self._on_task_button)
        self.btn_task_edit.clicked.connect(self.task_edit_requested.emit)
        self.btn_task_clear.clicked.connect(self.task_clear_requested.emit)
        controls.addLayout(buttons)

        self._left_layout.addWidget(info_box)
        self._left_layout.addWidget(self._split_box)
        self._left_layout.addWidget(controls_box)

        # ---- 우: 가로 모드에서 TODO 가 들어가는 칼럼 ----
        self._col_separator = self._separator(vertical=True)
        self._right_col = QWidget()
        self._right_layout = QVBoxLayout(self._right_col)
        self._right_layout.setContentsMargins(0, 0, 0, 0)

        root.addWidget(self._left_col)
        root.addWidget(self._col_separator)
        root.addWidget(self._right_col, 1)

        # ---- TODO 리스트 (높이를 늘리면 이 영역만 커짐 / 위치는 _apply_orientation) ----
        self.todo_panel = TodoPanel(
            lambda: snippets.from_config(self._cfg),
            lambda: widget_config.custom_tags(self._cfg),
            self._add_custom_tag,
            lambda: widget_config.undo_limit(self._cfg),
            self._confirm_todo_delete,
            page_id=todo_pages.last_page(),  # 프로필(DB)마다 따로 기억한다
            show_pending=lambda: widget_config.show_pending_page(self._cfg),
            remember_scroll=lambda: widget_config.remember_scroll(self._cfg),
        )
        self.todo_panel.export_requested.connect(self._export_todos)
        self.todo_panel.import_requested.connect(self._import_todos)
        self.todo_panel.page_changed.connect(self._save_todo_page)
        self.todo_panel.pending_visibility_changed.connect(self._save_show_pending)

        # 세로 모드에서 폭을 바꾸면 업무명 배지 말줄임을 다시 (자식을 다 만든 뒤에 건다)
        self._left_col.installEventFilter(self)
        self.apply_task(None)

    def apply_appearance(self):
        """현재 테마(theme.current())로 색 / 글꼴을 다시 입힌다. 글자 크기는 좌패널 배율을 따른다."""
        t = theme.current()
        s = t.left_scale
        sub_style = f"font-size: {px(11, s)}px; color: {t.text_sub};"
        # WA_TranslucentBackground 사용 시 자식 위젯이 배경을 불투명하게 덮으므로
        # QLabel 배경을 반드시 transparent 로 강제해야 한다.
        # 우클릭 메뉴(입력칸 기본 메뉴 포함)는 앱 스타일 ui/menus.MenuStyle 이 그린다 - QMenu 규칙은 넣지 않는다
        self.setStyleSheet(
            theme.button_style(t, px(12, s))
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QPushButton#profile {{
                font-size: {px(11, s)}px;
                color: {t.text_sub};
                padding: 1px 7px;
            }}
            QPushButton#profile:hover {{ color: {t.text_main}; }}
            """
        )
        painted.set_boxes(
            self,
            [
                (
                    QPushButton,
                    "profile",
                    painted.box(
                        PROFILE_CHIP_RADIUS,
                        t.overlay_color(14),
                        hover_bg=t.overlay_color(36),
                        down_bg=t.overlay_color(52),
                    ),
                ),
                (QPushButton, None, painted.button_box(t)),
            ],
        )
        self.name_edit.setStyleSheet(
            f"""
            QLineEdit {{
                {self._name_font()}
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
                border: 1px solid transparent;
                padding: 0px 4px;
                selection-background-color: {t.accent};
                selection-color: {t.on_accent};
            }}
            """
        )
        painted.set_box(
            self.name_edit,
            painted.box(
                painted.EDITABLE_RADIUS, t.overlay_color(18), t.overlay_color(90)
            ),
        )
        self.now_label.setStyleSheet(f"font-size: {px(12, s)}px; color: {t.text_sub};")
        self.remaining_caption.setStyleSheet(sub_style)
        for lb in (self.in_label, self.out_label):
            lb.setStyleSheet(f"font-size: {px(12, s)}px;")
        # 등록한 Task 의 업무명 배지 - 강조색 계열의 옅은 배경 + 테두리
        self.task_title_label.setStyleSheet(
            f"""
            font-size: {px(12, s)}px;
            font-weight: bold;
            color: {t.text_main};
            background: transparent;
            border: 1px solid transparent;
            padding: 5px 8px;
            """
        )
        badge_bg, badge_border = QColor(t.accent), QColor(t.accent)
        badge_bg.setAlpha(40)
        badge_border.setAlpha(170)
        painted.set_box(self.task_title_label, painted.box(6, badge_bg, badge_border))
        self.task_detail_label.setStyleSheet(sub_style)
        detail_bg = QColor(t.accent)
        detail_bg.setAlpha(DETAIL_CARD_BG_ALPHA)
        painted.set_box(self._detail_card, painted.box(CARD_RADIUS, detail_bg))
        self._split_handle.update()
        self.task_history.apply_appearance()
        for line in self._separators:
            line.setStyleSheet(f"background: {t.line}; border: none;")
        self.todo_panel.apply_appearance()

        self.set_user_name(self._cfg.get("user_name", ""))
        self._refresh_profile_chip()  # 글자 배율이 바뀌면 말줄임 폭도 바뀐다
        self._set_remaining_style(warn=self.remaining_label.text().startswith("+"))
        self._apply_task_dot(self._has_task())
        if self._task_title:
            self._set_task_title(self._task_title)
        self._set_task_detail(self._task_detail, resize=False)
        if self._orientation is not None:  # 배율이 바뀌면 최소 높이도 바뀐다
            self._apply_size_limits()
            self._place_grip()
        self._apply_opacity()

    def _min_height(self) -> int:
        """글자 배율을 키우면 좌패널 내용이 기본 최소 높이보다 커질 수 있다."""
        self.ensurePolished()  # 아직 띄우기 전이어도 스타일시트 글꼴로 크기를 재도록
        self._left_layout.invalidate()
        needed = self._left_col.minimumSizeHint().height() + CONTENT_MARGIN_V * 2
        return max(WIDGET_MIN_HEIGHT, needed)

    def _apply_orientation(self, orientation: str):
        """세로: info / TODO / 상세업무 / controls 를 한 줄로
        가로: 좌측은 info / _split_box(업무 이력 · 여백 · 끄는 선 · 상세업무) / controls, 우측에 TODO.
        가로 모드의 남는 높이는 업무 이력이 받는다 (이력을 껐으면 상세업무 위 여백)."""
        if orientation == self._orientation:
            return

        # 좌측 칼럼의 index 1 자리(info 와 _split_box 사이)에서 TODO 를 뺀다 (세로 모드였으면)
        if self._orientation == ORIENTATION_HORIZONTAL:
            self._right_layout.removeWidget(self.todo_panel)
        elif self._orientation == ORIENTATION_VERTICAL:
            self._left_layout.removeWidget(self.todo_panel)

        horizontal = orientation == ORIENTATION_HORIZONTAL
        if horizontal:
            self._right_layout.addWidget(self.todo_panel)
        else:
            self._left_layout.insertWidget(1, self.todo_panel, 1)
        # 가로: _split_box 가 남는 높이를 받는다 (업무 이력 또는 여백) / 세로: TODO 가 받는다
        self._left_layout.setStretchFactor(self._split_box, 1 if horizontal else 0)
        self.todo_panel.show()  # 다른 부모로 옮기면 숨김 상태가 되므로
        self._orientation = orientation
        self._apply_split()

        if horizontal:
            self._left_col.setFixedWidth(LEFT_COL_WIDTH)
        else:
            self._left_col.setMinimumWidth(LEFT_COL_WIDTH)
            self._left_col.setMaximumWidth(QWIDGETSIZE_MAX)

        # 숨긴 위젯은 레이아웃에서 자리/간격을 차지하지 않는다
        self._col_separator.setVisible(horizontal)
        self._right_col.setVisible(horizontal)

        self._apply_size_limits()
        self._place_grip()

    def _apply_split(self):
        """업무 이력 / 끄는 선 / 상세업무 카드 배치 (방향 · 업무 이력 켜기 · 상세업무가 바뀔 때마다)
        - 가로 + 업무 이력 켬: 이력이 남는 높이, 상세업무 카드는 cfg task_detail_lines 줄 (선을 끌어 정함)
        - 가로 + 업무 이력 끔: 상세업무 카드는 내용만큼 아래에 붙고 위는 여백 (넘치면 …)
        - 세로: 상세업무 카드는 내용만큼 3줄까지 (남는 높이는 TODO)"""
        horizontal = self._orientation == ORIENTATION_HORIZONTAL
        history = horizontal and self._history_on
        detail = bool(self._task_detail)
        card = self._detail_card
        self.task_history.setVisible(history)
        self._split_handle.setVisible(history and detail)
        card.setVisible(detail)
        if history:
            card.set_lines(widget_config.task_detail_lines(self._cfg))
            card.label.set_max_lines(None)  # 카드 높이만큼
        else:
            card.set_lines(None)
            card.label.set_max_lines(None if horizontal else TASK_DETAIL_MAX_LINES)
        # 세로 모드에서 안이 모두 숨으면 박스도 숨겨 간격이 생기지 않게 (가로 모드는 controls 를 바닥에 붙이는 여백)
        self._split_box.setVisible(horizontal or detail)

    # ---- 업무 이력 / 상세업무 사이 선 끌기 (_SplitHandle) ----
    def _on_split_start(self):
        card = self._detail_card
        spare = self.task_history.height() - self.task_history.minimumSizeHint().height()
        self._split_origin = (
            card.height(),
            card.label._line_height(),
            card.height() + max(0, spare),  # 업무 이력이 최소 높이까지 내줄 수 있는 만큼
        )

    def _on_split_drag(self, dy: float):
        """위로 끌면 상세업무 카드가 커지고 업무 이력이 줄어든다 - 줄 단위로 맞춘다."""
        if self._split_origin is None:
            return
        start_height, line, max_height = self._split_origin
        card = self._detail_card
        fits = max(1, (max_height - card.margins_v()) // line)
        lines = round((start_height - dy - card.margins_v()) / line)
        card.set_lines(max(1, min(lines, fits, widget_config.TASK_DETAIL_LINES_MAX)))

    def _on_split_end(self):
        self._split_origin = None
        lines = self._detail_card.lines
        if lines is not None and lines != widget_config.task_detail_lines(self._cfg):
            self._cfg["task_detail_lines"] = lines
            widget_config.save_config(self._cfg)

    def _on_split_reset(self):
        """끄는 선 더블클릭: 기본 줄 수(3줄)로"""
        self._split_origin = None
        self._cfg["task_detail_lines"] = widget_config.DEFAULT_TASK_DETAIL_LINES
        widget_config.save_config(self._cfg)
        self._apply_split()

    def set_task_history(self, entries, enabled: bool, now: datetime):
        """업무 이력 표시 (TaskPinApp._refresh_history). enabled=False 면 이력란을 숨긴다."""
        changed = enabled != self._history_on
        self._history_on = enabled
        if enabled:
            self.task_history.set_entries(entries, now)
        if changed and self._orientation is not None:
            self._apply_split()
            self._apply_size_limits()  # 이력란 최소 높이만큼 위젯 최소 높이가 바뀐다
            self._place_grip()

    def _apply_size_limits(self):
        """크기 범위를 지금 모드로 건다 - 최소는 모드마다(_limits), 최대는 가장 작은 모니터의 80%.
        모드마다 따로 저장한 폭 / 높이로 맞춘다 (세로: vertical_width / height, 가로: width / horizontal_height)."""
        min_width, min_height, max_width, max_height = self._limits()
        # 이전 모드의 min/max 와 엇갈리지 않도록 범위를 먼저 풀고 다시 건다
        self.setMinimumSize(0, 0)
        self.setMaximumSize(max_width, max_height)
        self.setMinimumSize(min_width, min_height)
        if self._orientation == ORIENTATION_HORIZONTAL:
            keys = ("width", "horizontal_height")
        else:
            keys = ("vertical_width", "height")
        self.resize(
            self._cfg_size(keys[0], min_width, min_width, max_width),
            self._cfg_size(keys[1], min_height, min_height, max_height),
        )

    def _watch_screens(self):
        """모니터를 붙이거나 떼거나 작업 영역(작업 표시줄)이 바뀌면 최대 크기를 다시 잰다."""
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(lambda _screen: self._on_screens_changed())
        for screen in QGuiApplication.screens():
            screen.availableGeometryChanged.connect(self._on_screens_changed)

    def _on_screen_added(self, screen):
        screen.availableGeometryChanged.connect(self._on_screens_changed)
        self._on_screens_changed()

    def _on_screens_changed(self, *_):
        if self._orientation is not None:
            self._apply_size_limits()
            self._place_grip()

    def _separator(self, vertical: bool = False) -> QFrame:
        line = QFrame()
        if vertical:
            line.setFrameShape(QFrame.VLine)
            line.setFixedWidth(1)
        else:
            line.setFrameShape(QFrame.HLine)
            line.setFixedHeight(1)
        self._separators.append(line)  # 색은 apply_appearance 에서
        return line

    def _opacity(self) -> float:
        """설정의 불투명도 (설정창 투명도 슬라이더 = 100 - 불투명도 %)"""
        return widget_config.opacity(self._cfg)

    def apply_opacity(self):
        """설정창 투명도 슬라이더가 바뀜 (저장은 설정창이 한다)"""
        self._apply_opacity()

    def _apply_opacity(self):
        """글자도 함께 투명(Appearance fade_text): 창 전체 불투명도
        해제(기본): 창은 불투명하게 두고 paintEvent 가 배경만 반투명하게 칠한다"""
        fade_text = theme.current().fade_text
        self.setWindowOpacity(self._opacity() if fade_text else 1.0)
        self.update()

    def save_size(self):
        """조절한 크기 저장 - 모드마다 폭과 높이를 따로 저장한다"""
        if self._orientation == ORIENTATION_HORIZONTAL:
            self._cfg["width"] = self.width()
            self._cfg["horizontal_height"] = self.height()
        else:
            self._cfg["vertical_width"] = self.width()
            self._cfg["height"] = self.height()
        widget_config.save_config(self._cfg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_grip()

    def set_input_blocked(self, blocked: bool):
        """Task 등록 / 수정 창이 떠 있는 동안 위젯을 투명한 막으로 덮는다 (끌어 옮기기만 된다).
        막이 포커스를 가져가 이 창을 다시 활성화해도 단축키 / 키 입력이 아래로 가지 않는다."""
        if blocked:
            self._blocker.setGeometry(self.rect())
            self._blocker.show()
            self._blocker.raise_()
            self._blocker.setFocus(Qt.OtherFocusReason)
        elif not self._blocker.isHidden():
            if self._blocker.hasFocus() or self.focusWidget() is self._blocker:
                # 포커스를 가진 위젯을 숨기면 Qt 가 다음 위젯으로 넘기며 목록을 스크롤한다 - 목록으로 먼저
                self.todo_panel.container.setFocus(Qt.OtherFocusReason)
            self._blocker.hide()

    def _place_grip(self):
        """하단(높이) / 우측(폭) 핸들. 둥근 모서리 구간은 비워 둔다."""
        self._grip_v.setGeometry(
            CORNER_RADIUS,
            self.height() - RESIZE_MARGIN,
            self.width() - CORNER_RADIUS * 2,
            RESIZE_MARGIN,
        )
        self._grip_h.setGeometry(
            self.width() - RESIZE_MARGIN,
            CORNER_RADIUS,
            RESIZE_MARGIN,
            self.height() - CORNER_RADIUS * 2,
        )
        self._grip_v.raise_()
        self._grip_h.raise_()
        blocker = getattr(self, "_blocker", None)  # 처음 배치할 때는 아직 없다
        if blocker is not None and not blocker.isHidden():
            blocker.setGeometry(self.rect())
            blocker.raise_()  # 막은 크기 조절 핸들보다도 위 (크기 조절도 막는다)

    def _set_grips_enabled(self, enabled: bool):
        for grip in (self._grip_v, self._grip_h):
            grip.set_enabled(enabled)
        self._split_handle.set_enabled(enabled)  # 위치 / 크기 잠금이면 상세업무 높이도 끌지 않는다

    def _set_remaining_style(self, warn: bool):
        t = theme.current()
        color = t.text_warn if warn else t.text_main
        self.remaining_label.setStyleSheet(
            f"font-size: {px(28, t.left_scale)}px; font-weight: bold; color: {color};"
        )

    @staticmethod
    def _name_font() -> str:
        return f"font-size: {px(15, theme.current().left_scale)}px; font-weight: bold;"

    def _apply_task_dot(self, registered: bool):
        """Task 시간이 등록되어 있으면 초록 점, 없으면 빈 원"""
        radius = self.status_dot.width() / 2
        painted.set_box(
            self.status_dot,
            painted.box(radius, TASK_DOT_COLOR)
            if registered
            else painted.box(radius, None, theme.current().text_sub, width=1.5),
        )

    # ==================================================
    # 외부(TaskPinApp)에서 호출하는 슬롯
    # ==================================================
    def apply_task(self, task):
        """현재 Task 표시. task 는 None 또는 title / start_at / end_at 을 가진 객체"""
        if task is None:
            self.in_label.setText("시작 --:--")
            self.out_label.setText("종료 --:--")
            self._task_title = ""
            self.task_title_label.hide()
            self._set_task_detail("")
        else:
            self.in_label.setText(f"시작 {task.start_at:%H:%M}")
            self.out_label.setText(f"종료 {task.end_at:%H:%M}")
            self._set_task_title(task.title)
            self._set_task_detail(task.detail)
        registered = task is not None
        self.btn_task.setText(
            TASK_BUTTON_RELEASE if registered else TASK_BUTTON_REGISTER
        )
        self.btn_task.setToolTip("진행 중인 Task 해제" if registered else "Task 등록")
        self.btn_task_edit.setEnabled(registered)
        self.btn_task_clear.setEnabled(registered)
        self._apply_task_dot(task is not None)

    def _set_task_title(self, title: str):
        """배지는 한 줄 - 길면 말줄임하고 전체는 툴팁으로"""
        self._task_title = title
        label = self.task_title_label
        label.ensurePolished()  # 스타일시트 글꼴(굵게)로 폭을 재기 위해
        width = self._left_col.width() - TASK_BADGE_H_SPACE
        shown = label.fontMetrics().elidedText(title, Qt.ElideRight, width)
        label.setText(shown)
        label.setToolTip(title if shown != title else "")
        label.setVisible(bool(title))

    def _set_task_detail(self, detail: str, resize: bool = True):
        """상세업무 표시 (줄 수 / 말줄임은 _DetailLabel 이 받은 높이에 맞춘다, 배치는 _apply_split).
        보이고 숨는 것이 바뀌면 좌패널 최소 높이(위젯 최소 높이)를 다시 맞춘다."""
        self._task_detail = detail
        card = self._detail_card
        changed = card.isHidden() == bool(detail)
        card.label.set_full_text(detail)
        self._apply_split()
        if changed and resize and self._orientation is not None:
            self._apply_size_limits()
            self._place_grip()

    def set_user_name(self, name: str):
        t = theme.current()
        self.name_label.setText(name or "이름")
        self.name_label.set_text_style(
            f"{self._name_font()} color: {t.text_main if name else t.text_dim};"
        )

    # ==================================================
    # 사용자 이름 편집 (더블클릭)
    # ==================================================
    def eventFilter(self, obj, event):
        if obj is self.name_label and event.type() == QEvent.MouseButtonDblClick:
            self.start_name_edit()
            return True
        if obj is self._left_col and event.type() == QEvent.Resize and self._task_title:
            self._set_task_title(
                self._task_title
            )  # 세로 모드 폭을 바꾸면 배지 폭도 바뀐다
        return super().eventFilter(obj, event)

    def start_name_edit(self):
        self.name_label.hide()
        self.name_edit.setText(self._cfg.get("user_name", ""))
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _commit_name_edit(self):
        if not self.name_edit.isVisible():
            return  # Enter 로 저장한 뒤 포커스 이동으로 한 번 더 오는 경우
        name = self.name_edit.text().strip()
        self._finish_name_edit()
        if name != self._cfg.get("user_name", ""):
            self._cfg["user_name"] = name
            widget_config.save_config(self._cfg)
            self.set_user_name(name)

    def _finish_name_edit(self):
        self.name_edit.hide()
        self.name_label.show()

    def apply_shortcuts(self, mapping: dict):
        """단축키를 다시 건다. mapping: {동작: QKeySequence PortableText} ("" 이면 해제)"""
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = []
        # 목록 키(위 / 아래 / 접기 / 펼치기)는 창 단축키로 걸지 않는다 - 입력칸의 화살표를 가로채지 않게
        # 목록에 포커스가 있을 때(또는 포커스 위젯이 없을 때)만 TodoPanel 이 받는다
        self.todo_panel.set_nav_keys(mapping)

        handlers = {
            "task_register": self._on_task_button,
            "task_edit": self._on_edit_shortcut,
            "task_clear": self._on_clear_shortcut,
            "todo_focus": self.todo_panel.focus_input,
            "todo_edit": lambda: self.todo_panel.edit_current(
                rename_page=mapping.get("todo_edit") == FIXED_EDIT_KEY
            ),
            "todo_search": self.todo_panel.open_search,
            "todo_page_prev": lambda: self.todo_panel.step_page(-1),
            "todo_page_next": lambda: self.todo_panel.step_page(1),
            "todo_page_first": lambda: self.todo_panel.go_page_edge(last=False),
            "todo_page_last": lambda: self.todo_panel.go_page_edge(last=True),
            "todo_page_new": self.todo_panel.add_page,
            "todo_page_jump": self.todo_panel.open_page_switcher,
            "todo_undo": self.todo_panel.undo,
            "todo_redo": self.todo_panel.redo,
            "settings": self.settings_requested.emit,
        }
        for action, keys in mapping.items():
            sequence = QKeySequence(keys, QKeySequence.PortableText)
            if action not in handlers or sequence.isEmpty():
                continue
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(handlers[action])
            self._shortcuts.append(shortcut)
        # 고정 키: 할 일 수정 F2(선택이 없으면 페이지 이름 바꾸기), 되돌리기 Ctrl+Z, 다시 실행 Ctrl+Y / Ctrl+Shift+Z.
        # 설정 키를 바꿔도 함께 된다. 어떤 설정 키가 고정 키와 같거나 앞부분이 겹치면 같은 키의 단축키가 둘이 되어
        # 둘 다 듣지 않으므로 그 고정 키는 걸지 않는다 (같은 동작이면 설정 키가 이미 듣는다)
        fixed_keys = [(FIXED_EDIT_KEY, lambda: self.todo_panel.edit_current(rename_page=True))]
        fixed_keys += [(keys, self.todo_panel.undo) for keys in FIXED_UNDO_KEYS]
        fixed_keys += [(keys, self.todo_panel.redo) for keys in FIXED_REDO_KEYS]
        for fixed_text, handler in fixed_keys:
            fixed = QKeySequence(fixed_text, QKeySequence.PortableText)
            if any(
                QKeySequence(keys, QKeySequence.PortableText).matches(fixed)
                != QKeySequence.NoMatch
                or fixed.matches(QKeySequence(keys, QKeySequence.PortableText))
                != QKeySequence.NoMatch
                for keys in mapping.values()
                if keys
            ):
                continue
            shortcut = QShortcut(fixed, self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _has_task(self) -> bool:
        return self.btn_task_clear.isEnabled()

    def _on_task_button(self):
        """[등록/해제] 버튼 / 단축키: Task 가 없으면 등록, 진행 중이면 해제(확인 창은 TaskPinApp)"""
        if self._has_task():
            self.task_release_requested.emit()
        else:
            self.task_register_requested.emit()

    def _on_edit_shortcut(self):
        if self._has_task():
            self.task_edit_requested.emit()

    def _on_clear_shortcut(self):
        if self._has_task():
            self.task_clear_requested.emit()

    def _add_custom_tag(self, name: str, color: str) -> str:
        """우패널 태그 메뉴 "+ 태그 추가…": 사용자 태그를 config.json 에 저장하고 id 를 돌려준다."""
        tag_id = widget_config.add_custom_tag(self._cfg, name, color)
        widget_config.save_config(self._cfg)
        return tag_id

    def _save_todo_page(self, page_id: int):
        """마지막으로 본 TODO 페이지 - 다음 실행 / 이 프로필로 돌아올 때 그 페이지부터 보여준다.
        페이지 id 는 DB 마다 다르므로 설정이 아니라 프로필 DB 에 둔다."""
        todo_pages.set_last_page(page_id)

    def _save_show_pending(self, visible: bool):
        """페이지 우클릭 "미완료 페이지 표시" (모든 프로필이 함께 쓰는 설정)"""
        self._cfg["show_pending_page"] = visible
        widget_config.save_config(self._cfg)

    def _confirm_todo_delete(self, count: int) -> bool:
        """할 일 삭제(행의 ✕ / 우클릭 "삭제"): 지우기 전에 묻는다. "다시 묻지 않음"을 켜고 삭제하면
        설정에 남겨 다음부터 묻지 않는다 (설정창 Application 에서 다시 켤 수 있다)."""
        if not widget_config.confirm_delete(self._cfg):
            return True
        dialog = ConfirmDialog(
            "할 일 삭제",
            "선택된 항목을 삭제하시겠습니까?"
            if count == 1
            else f"선택된 항목 {count}개를 삭제하시겠습니까?",
            confirm_text="삭제",
            note="Ctrl+Z 나 우클릭 → 삭제 이력으로 되돌릴 수 있습니다.",
            danger=True,
            remember_text="다시 묻지 않음",
            parent=self,
        )
        if not dialog.exec_over(self):
            return False
        if dialog.remembered():
            self._cfg["confirm_delete"] = False
            widget_config.save_config(self._cfg)
        return True

    def set_clock(self, now_text: str, remaining_text: str):
        self.now_label.setText(f"현재시간  {now_text}")
        self.remaining_label.setText(remaining_text)
        self._set_remaining_style(warn=remaining_text.startswith("+"))

    # ==================================================
    # 반투명 둥근 배경
    # ==================================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        t = theme.current()
        bg = QColor(t.bg)
        if not t.fade_text:  # 글자는 두고 배경만 투명하게
            bg.setAlphaF(self._opacity())
        painter.fillPath(path, bg)

    def keyPressEvent(self, event):
        """포커스 위젯이 없을 때(좌패널을 클릭한 뒤 등) 받은 위 / 아래 / Home / End 같은 목록 키는
        TODO 목록으로 넘겨 바로 할 일을 고르게 한다."""
        idle = QApplication.focusWidget() in (None, self)
        if idle and self.todo_panel.handle_nav_key(event.key(), event.modifiers()):
            return
        super().keyPressEvent(event)

    # ==================================================
    # 드래그 이동
    # ==================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._locked:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()

    # ==================================================
    # 위치 저장 / 복원
    # ==================================================
    def _save_position(self):
        pos = self.pos()
        self._cfg["pos"] = [pos.x(), pos.y()]
        widget_config.save_config(self._cfg)

    def _restore_position(self):
        pos = self._cfg.get("pos")
        if (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and self._is_on_any_screen(QPoint(int(pos[0]), int(pos[1])))
        ):
            self.move(int(pos[0]), int(pos[1]))
        else:
            self._move_to_top_right()

    @staticmethod
    def _is_on_any_screen(point: QPoint) -> bool:
        """모니터 구성이 바뀌어 저장 좌표가 화면 밖이 된 경우를 걸러낸다."""
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(point):
                return True
        return False

    def _move_to_top_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - SCREEN_MARGIN,
            screen.top() + SCREEN_MARGIN,
        )

    # ==================================================
    # 우클릭 컨텍스트 메뉴
    # ==================================================
    def contextMenuEvent(self, event):
        """좌패널(Task) 메뉴. TODO 목록 위에서는 TodoPanel 이 자기 메뉴를 띄운다.
        포커스 위젯이 없을 때 누른 메뉴 키는 고른 할 일이 있으면 그 할 일의 메뉴를 띄운다
        (↑↓ 같은 목록 키를 목록으로 넘기는 것과 같이)."""
        if (
            event.reason() == QContextMenuEvent.Keyboard
            and self.todo_panel.has_current()
        ):
            self.todo_panel.show_current_menu()
            return
        menu = QMenu(self)

        if self._orientation == ORIENTATION_HORIZONTAL:
            menu.addAction(
                menus.icon("rotate"),
                "세로 모드",
                lambda: self.set_orientation(ORIENTATION_VERTICAL),
            )
        else:
            menu.addAction(
                menus.icon("rotate"),
                "가로 모드",
                lambda: self.set_orientation(ORIENTATION_HORIZONTAL),
            )

        act_lock = menu.addAction(menus.icon("lock"), "위치/크기 잠금")
        act_lock.setCheckable(True)
        act_lock.setChecked(self._locked)
        act_lock.toggled.connect(self.set_locked)

        # 다른 앱을 보며 등록 / 할 일 추가를 할 때 위젯이 뒤로 사라지지 않게
        act_top = menu.addAction(menus.icon("pin"), "항상 위에 보이기")
        act_top.setCheckable(True)
        act_top.setChecked(self._cfg_on_top())
        act_top.toggled.connect(self.set_always_on_top)

        act_auto = menu.addAction(menus.icon("startup"), "윈도우 시작 시 실행")
        act_auto.setCheckable(True)
        act_auto.setChecked(os_win.is_autostart_enabled())
        act_auto.toggled.connect(self._on_autostart_toggled)

        menu.addSeparator()
        if self._profile_menu_filler is not None:
            # 헬퍼가 채우는 서브메뉴는 부모를 줘야 참조가 사라져도 지워지지 않는다
            sub = QMenu(f"프로필 · {self._profile_name}".replace("&", "&&"), menu)
            sub.setIcon(menus.icon("profile"))
            self._profile_menu_filler(sub)
            menu.addMenu(sub)
        menu.addAction(menus.icon("settings"), "설정", self.settings_requested.emit)
        menu.addAction(menus.icon("hide"), "위젯 숨기기", self.hide_widget)
        menu.addSeparator()
        menu.addAction(menus.icon("power"), "프로그램 종료", self.quit_requested.emit)

        menu.exec(event.globalPos())

    # ==================================================
    # 프로필 (DB 파일 하나 = 프로필 하나 - 목록 / 바꾸기는 TaskPinApp, manager/profiles)
    # ==================================================
    def set_profile_menu(self, filler):
        """filler: (QMenu) -> None. 우클릭 "프로필" 서브메뉴와 헤더 칩 메뉴를 채운다 (열 때마다 다시)."""
        self._profile_menu_filler = filler

    def set_profile(self, name: str, show_chip: bool):
        """지금 프로필 이름. show_chip: 헤더 오른쪽에 칩으로 보일지 (프로필이 둘 이상일 때)"""
        self._profile_name = name
        self.profile_button.setVisible(show_chip)
        self._refresh_profile_chip()

    def _refresh_profile_chip(self):
        """칩 글자: 긴 이름은 말줄임 + 툴팁. & 는 단축 글자 표시가 되므로 && 로"""
        font = self.font()
        font.setPixelSize(px(11, theme.current().left_scale))
        width = px(PROFILE_CHIP_MAX_WIDTH, theme.current().left_scale)
        text = QFontMetrics(font).elidedText(self._profile_name, Qt.ElideRight, width)
        self.profile_button.setText(text.replace("&", "&&"))
        self.profile_button.setToolTip(
            f"프로필: {self._profile_name}\n눌러서 프로필 바꾸기"
        )

    def _show_profile_menu(self):
        """헤더 프로필 칩: 칩 바로 아래에 프로필 메뉴 (우클릭 "프로필" 서브메뉴와 같은 내용)"""
        if self._profile_menu_filler is None:
            return
        menu = QMenu(self)
        self._profile_menu_filler(menu)
        btn = self.profile_button
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def finish_editing(self):
        """프로필(DB)을 바꾸기 전에: 그 자리에서 고치던 할 일을 지금 DB 에 저장한다."""
        self.todo_panel.finish_editing()

    def _export_todos(self, kind: str):
        """우패널 "내보내기": TODO 를 Markdown 체크리스트 파일로 저장한다. 마지막 저장 폴더를 기억한다.
        kind: todo_export.PAGE 현재 페이지 / ALL 전체 페이지 / ARCHIVED 보관 항목 전체.
        파일 창이 떠 있는 동안은 "항상 위" 설정과 관계없이 위에 둔다 (다른 앱 뒤로 숨지 않게)."""
        now = datetime.now()
        panel = self.todo_panel
        page_name = panel.page_name()  # 현재 페이지는 제목 / 파일 이름에 넣는다
        if kind == todo_export.ARCHIVED:
            # 보관 항목의 상위는 어느 페이지에든 남아 있을 수 있다
            text = todo_export.archived_to_markdown(
                todo_store.load_archived(), now, panel.all_items()
            )
        elif kind == todo_export.ALL:
            text = todo_export.pages_to_markdown(panel.pages(), panel.all_items(), now)
        elif panel.is_pending_page():
            text = todo_export.pending_to_markdown(
                panel.pages(), panel.items(), now, page_name
            )
        else:
            text = todo_export.to_markdown(panel.items(), now, page_name)

        folder = self._cfg.get("export_dir") or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation
        )
        self.hold_on_top("export", True)
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "TODO 내보내기",
                os.path.normpath(
                    os.path.join(
                        folder, todo_export.default_filename(kind, now, page_name)
                    )
                ),
                "Markdown (*.md)",
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError as e:
                QMessageBox.warning(
                    self, "TODO 내보내기", f"파일을 저장하지 못했습니다.\n{e}"
                )
                return
        finally:
            self.hold_on_top("export", False)
        self._cfg["export_dir"] = os.path.dirname(path)
        widget_config.save_config(self._cfg)

    def _import_todos(self, mode: str):
        """우패널 "가져오기": Markdown 체크리스트 파일을 새 페이지의 할 일로 넣는다 (지금 페이지는 그대로).
        mode: todo_import.SINGLE 한 페이지로 / SECTIONS ## 섹션마다 페이지로.
        시작 폴더는 내보내기와 같은 마지막 폴더(cfg export_dir). 파일 창 / 확인 창이 떠 있는 동안은 위에 둔다."""
        title = "TODO 가져오기"
        folder = self._cfg.get("export_dir") or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation
        )
        self.hold_on_top("import", True)
        try:
            path, _ = QFileDialog.getOpenFileName(
                self,
                title,
                os.path.normpath(folder),
                "Markdown (*.md *.markdown *.txt);;모든 파일 (*)",
            )
            if not path:
                return
            try:
                text = todo_import.read_file(path)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, title, f"파일을 읽지 못했습니다.\n{e}")
                return
            self._cfg["export_dir"] = os.path.dirname(path)
            widget_config.save_config(self._cfg)
            pages = todo_import.parse(
                text, mode, todo_import.page_name_from_file(path)
            )
            if not pages:
                QMessageBox.information(
                    self,
                    title,
                    "가져올 할 일이 없습니다.\n'- [ ] 할 일' 같은 목록 줄을 할 일로 가져옵니다.",
                )
                return
            count = sum(len(page["items"]) for page in pages)
            names = [page["name"] for page in pages]
            note = ", ".join(f"'{name}'" for name in names[:4])
            if len(names) > 4:
                note += f" 외 {len(names) - 4}장"
            dialog = ConfirmDialog(
                title,
                f"새 페이지 {len(pages)}장에 할 일 {count}개를 가져올까요?",
                confirm_text="가져오기",
                note=note,
                parent=self,
            )
            if not dialog.exec_over(self):
                return
        finally:
            self.hold_on_top("import", False)
        self.todo_panel.import_pages(pages)

    def set_locked(self, locked: bool):
        self._locked = locked
        self._set_grips_enabled(not locked)
        self._cfg["locked"] = locked
        widget_config.save_config(self._cfg)

    def set_orientation(self, orientation: str):
        self._cfg["orientation"] = orientation
        widget_config.save_config(self._cfg)
        self._apply_orientation(orientation)
        self._keep_on_screen()

    def _keep_on_screen(self):
        """폭이 넓어져 화면 오른쪽을 벗어나면 화면 안으로 당긴다."""
        geo = self.frameGeometry()
        screen = QApplication.screenAt(geo.topLeft()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = max(area.left(), min(geo.left(), area.right() + 1 - geo.width()))
        if x != geo.left():
            self.move(x, geo.top())
            self._save_position()

    def set_always_on_top(self, on_top: bool):
        self._cfg["always_on_top"] = on_top
        widget_config.save_config(self._cfg)
        self._apply_stay_mode()

    def _apply_stay_mode(self):
        """항상 위 / 아래 힌트를 깜빡임 없이 바꾸고 Win32 z-order 를 맞춘다.
        setWindowFlags 는 창을 숨겼다 다시 띄우므로 _set_bottom_hint 처럼 플래그만 바꾼다.
        메뉴를 연 위젯은 '앞으로 꺼낸' 상태라 그대로 두면 _apply_z_order 가 건너뛰고,
        다른 앱으로 넘어갈 때 _send_to_back 이 바탕화면 층으로 내리므로 먼저 푼다."""
        self._front_timer.stop()
        self._front = False
        if self.windowHandle() is None:  # 아직 띄운 적 없음
            self._apply_window_flags()
            return
        flags = self.windowFlags() & ~(
            Qt.WindowStaysOnTopHint | Qt.WindowStaysOnBottomHint
        )
        flags |= (
            Qt.WindowStaysOnTopHint if self._on_top() else Qt.WindowStaysOnBottomHint
        )
        self.overrideWindowFlags(flags)
        self.windowHandle().setFlags(flags)
        self.repaint()
        self._apply_z_order()
        if not self._on_top() and (
            self.isActiveWindow() or os_win.is_own_window(os_win.foreground_window())
        ):
            # 끄자마자 사라지지 않게 - 다른 앱을 누르면 그때 바탕화면 층으로
            # (등록 창을 닫는 중이면 아직 그 창이 활성이라 전경 창이 이 앱의 창인지도 본다)
            self.bring_to_front()

    def reload_config(self):
        """설정 가져오기: 새 값으로 바뀐 cfg 를 위젯 배치 / 상태에 다시 적용한다.
        (테마 / 단축키는 TaskPinApp 이 apply_appearance / apply_shortcuts 로 따로 건다)"""
        self._locked = bool(self._cfg.get("locked", False))
        self._set_grips_enabled(not self._locked)
        self._apply_opacity()
        self.set_user_name(self._cfg.get("user_name", ""))
        self.todo_panel.sync_pending_page()  # 미완료 페이지 표시

        on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if on_top != self._on_top():
            self._apply_stay_mode()
        self._apply_orientation(self._cfg_orientation())
        self._apply_size_limits()  # 같은 모드여도 저장된 폭 / 높이로
        self._place_grip()
        self._restore_position()

        visible = bool(self._cfg.get("visible", True))
        if visible and not self.isVisible():
            self.show_widget()
        elif not visible and self.isVisible():
            self.hide_widget()

    def _on_autostart_toggled(self, enable: bool):
        if not os_win.set_autostart(enable):
            # 실패 시 체크 상태를 원복(다음 메뉴 오픈 시 레지스트리 값 기준으로 재구성됨)
            print("자동 실행 설정을 변경하지 못했습니다.")

    # ==================================================
    # 리마인더
    # ==================================================
    def reload_data(self, keep_copy: bool = False):
        """DB 가 바뀐 뒤 ("모든 데이터 초기화" / 프로필 바꾸기): 떠 있는 리마인더 알림을 닫고 할 일 목록을
        DB 에서 다시 읽어 그 DB 에서 마지막으로 본 페이지를 보여준다.
        keep_copy: 복사해 둔 할 일을 남긴다 (다른 프로필에 붙여넣기)"""
        for popup in list(self._popups):
            popup.close()
        self.todo_panel.reload(todo_pages.last_page(), keep_copy=keep_copy)

    def check_reminders(self):
        """시각이 된 리마인더를 팝업 + reminder_due 시그널로 알린다."""
        now = datetime.now().astimezone()
        for item in self.todo_panel.pop_due(now):
            text = todo_store.display_body(item["text"])  # 중요 항목의 "!" 는 빼고
            self._show_reminder_popup(item["id"], text, todo_store.due_at(item))
            self.reminder_due.emit(item["id"], text)
        self.todo_panel.refresh_rows()  # 지난 리마인더 색 갱신

    def _show_reminder_popup(self, item_id: str, text: str, due: datetime):
        popup = ReminderPopup(item_id, text, due)
        popup.done_requested.connect(lambda _id: self.todo_panel.set_done(_id, True))
        popup.snooze_requested.connect(self.todo_panel.snooze)
        popup.opened.connect(self.show_todo)
        popup.closed.connect(lambda p=popup: self._on_popup_closed(p))
        popup.destroyed.connect(lambda _=None, p=popup: self._on_popup_closed(p))
        self._popups.append(popup)
        popup.move(self._popup_slots(self._popups)[-1])
        popup.show()

    def show_todo(self, item_id: str):
        """알림 팝업을 누름: 위젯을 띄워 앞으로 꺼내고 그 할 일의 페이지로 가서 골라 깜빡인다."""
        if not self.isVisible():
            self.show_widget()  # visibility_changed 로 트레이 체크도 맞춰진다
        self.bring_to_front()
        self.todo_panel.reveal_item(item_id)

    def _on_popup_closed(self, popup):
        """알림이 닫힘(완료 / 나중에 / 닫기 / 눌러서 보기): 남은 알림을 위로 당긴다. 다른 알림은 그대로 둔다."""
        if popup in self._popups:
            self._popups.remove(popup)
            self._layout_popups()

    def _popup_slots(self, popups: list) -> list:
        """popups 를 차례로 놓을 자리. 위젯 위치와 상관없이 주 모니터 우측 상단부터 아래로 쌓고,
        아래 공간이 없으면 왼쪽 열로 넘어가 다시 위에서부터 쌓는다. (팝업 폭은 설정의 알림 창 크기)"""
        area = QApplication.primaryScreen().availableGeometry()
        top = area.top() + SCREEN_MARGIN
        bottom = area.bottom() + 1 - SCREEN_MARGIN
        right = area.right() + 1 - SCREEN_MARGIN
        slots, y = [], top
        for p in popups:
            if y > top and y + p.height() > bottom:
                right -= p.width() + POPUP_GAP
                y = top
            slots.append(QPoint(max(right - p.width(), area.left()), y))
            y += p.height() + POPUP_GAP
        return slots

    def _layout_popups(self):
        """남은 알림을 쌓는 규칙대로 다시 놓는다 - 위 알림이 닫히면 아래 알림이 미끄러지듯 올라온다."""
        for popup, pos in zip(self._popups, self._popup_slots(self._popups)):
            anim = getattr(popup, "_slide_anim", None)
            if anim is not None:
                anim.stop()  # 옮기는 중에 또 닫히면 새 자리로 다시
            if popup.pos() == pos:
                continue
            anim = QPropertyAnimation(popup, b"pos", popup)
            anim.setDuration(POPUP_SLIDE_MS)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setEndValue(pos)
            popup._slide_anim = anim
            anim.start()

    # ==================================================
    # 표시 / 숨김
    # ==================================================
    def hide_widget(self):
        self.hide()
        self._cfg["visible"] = False
        widget_config.save_config(self._cfg)
        self.visibility_changed.emit(False)

    def show_widget(self):
        self.show()
        self._cfg["visible"] = True
        widget_config.save_config(self._cfg)
        self.visibility_changed.emit(True)

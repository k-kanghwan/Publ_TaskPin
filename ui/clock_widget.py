"""바탕화면 Task 시간 위젯 (PySide6)

Priv_dtcal/dtcal_poc.py 에서 검증된 기법을 이식:
  - Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint
  - WA_TranslucentBackground + paintEvent 로 둥근 반투명 배경 직접 그리기
  - globalPosition() 오프셋 방식 드래그

이 위젯은 "멍청한 뷰"다. Task 저장 / 시간 계산은 전부 TaskPinApp 이 담당하고,
위젯은 시그널로 요청만 올려보낸 뒤 apply_task() / set_clock() 으로 값을 받아 그린다.
(사용자 이름 / TODO / 위젯 설정은 위젯이 직접 저장한다)

단축키(설정창 Keyboard Shortcuts 탭)는 위젯 창이 활성일 때만 동작한다. E/C/A 같은 글자 키는
입력칸이 먼저 가져가므로(ShortcutOverride) 할 일이나 이름을 입력하는 중에는 글자로 들어간다.
"""

import os
from datetime import datetime

from PySide6.QtCore import QEvent, QStandardPaths, Qt, QPoint, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from manager import os_win, snippets, todo_export, todo_store, widget_config
from ui import theme
from ui.reminder_popup import ReminderPopup
from ui.theme import CORNER_RADIUS, px
from ui.todo_panel import TodoPanel


# ========= ========= 테마 ========= =========
WINDOW_OPACITY = 1.0  # 설정에 값이 없을 때의 불투명도 (= 투명도 0%)
OPACITY_MIN = 0.2  # 이보다 낮으면 위젯이 사라져 조작 불가
TRANSPARENCY_MAX = round((1 - OPACITY_MIN) * 100)  # 슬라이더 최대 투명도(%) = 80
# 세로 모드: 좌우 고정 / 높이만 조절
WIDGET_WIDTH = 280
WIDGET_MIN_HEIGHT = 324
WIDGET_MAX_HEIGHT = int(WIDGET_MIN_HEIGHT * 1.5)  # 486
# 가로 모드: 상하 고정(WIDGET_MIN_HEIGHT) / 폭만 조절 - 좌 시간(280) + 우 TODO
WIDGET_MIN_WIDTH_HORIZONTAL = 540
WIDGET_MAX_WIDTH_HORIZONTAL = int(WIDGET_MIN_WIDTH_HORIZONTAL * 1.5)  # 810
RESIZE_MARGIN = 6  # 하단/우측 크기 조절 영역(px) - root 마진(14/16px) 안쪽
SCREEN_MARGIN = 24
CONTENT_MARGIN_H = 16  # root 좌우 마진
CONTENT_MARGIN_V = 14  # root 상하 마진
COLUMN_SPACING = 12  # 가로 모드 좌/우 칼럼 사이 간격

ORIENTATION_VERTICAL = "vertical"
ORIENTATION_HORIZONTAL = "horizontal"

FRONT_CHECK_MS = 300  # 앞으로 꺼낸 동안 다른 앱이 활성화됐는지 확인하는 주기
REMINDER_CHECK_MS = 20 * 1000  # 리마인더 확인 주기
REMINDER_STARTUP_DELAY_MS = 3 * 1000  # 앱이 꺼져있던 동안 지난 알림을 시작 직후 확인
POPUP_GAP = 8

TASK_DOT_COLOR = "#4caf50"  # Task 시간이 등록되어 있을 때 헤더의 점
USER_NAME_MAX_LEN = 20
TASK_BADGE_H_SPACE = 2 * 8 + 2 * 1  # 좌우 padding + border (말줄임 폭 계산용)
# ========= ========= ========= ========= =========


class _ResizeGrip(QWidget):
    """위젯 가장자리의 크기 조절 핸들 (세로 모드: 하단 / 가로 모드: 우측)

    부모 위젯의 mouseMoveEvent 로 커서를 바꾸면 자식 위젯 위에서 커서가
    원복되지 않으므로, 커서를 자체적으로 갖는 얇은 자식 위젯으로 분리한다.
    """

    def __init__(self, window: "ClockWidget"):
        super().__init__(window)
        self._window = window
        self._vertical = True  # True: 높이 조절 / False: 폭 조절
        self._origin = None  # (누른 지점의 global 좌표, 그때의 크기)
        self._hover = False

    def set_vertical(self, vertical: bool):
        self._vertical = vertical
        self.set_enabled(self.isEnabled())

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


class _NameEdit(QLineEdit):
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


class ClockWidget(QWidget):
    """바탕화면에 상주하는 Task 시간 + TODO 위젯"""

    task_register_requested = Signal()
    task_clear_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    visibility_changed = Signal(bool)
    reminder_due = Signal(str, str)  # item id, 본문

    def __init__(self, cfg: dict, force_on_top: bool = False):
        super().__init__()

        self._cfg = cfg
        # 디버그 실행: 설정과 관계없이 항상 위 (cfg 는 바꾸지 않으므로 저장되지 않는다)
        self._force_on_top = force_on_top
        self._locked = bool(cfg.get("locked", False))
        self._drag_offset = None
        self._popups = []
        self._shortcuts = []
        self._separators = []  # 테마가 바뀌면 다시 칠할 구분선
        self._task_title = ""  # 업무명 배지 원문 (말줄임 전)
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
        # 투명도는 오직 투명도 슬라이더로만 정한다 (배경색 자체는 불투명) - apply_appearance 의 _apply_opacity

        self._build_ui()
        self._grip = _ResizeGrip(self)
        self._grip.set_enabled(not self._locked)
        # 3) 크기 범위 / 조절 방향은 모드별로 (세로: 높이만, 가로: 폭만)
        self._orientation = None
        self._apply_orientation(self._cfg_orientation())
        self.apply_appearance()
        self._restore_position()
        self.apply_shortcuts(widget_config.shortcuts(self._cfg))

        # 4) 리마인더 (위젯이 숨겨져 있어도 계속 확인)
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(REMINDER_CHECK_MS)
        QTimer.singleShot(REMINDER_STARTUP_DELAY_MS, self.check_reminders)

    def _cfg_opacity(self) -> float:
        try:
            value = float(self._cfg.get("opacity", WINDOW_OPACITY))
        except (TypeError, ValueError):
            value = WINDOW_OPACITY
        return min(1.0, max(OPACITY_MIN, value))

    def _cfg_height(self) -> int:
        min_height = self._min_height()
        try:
            value = int(self._cfg.get("height") or min_height)
        except (TypeError, ValueError):
            value = min_height
        return min(max(WIDGET_MAX_HEIGHT, min_height), max(min_height, value))

    def _cfg_width(self) -> int:
        """가로 모드 폭"""
        try:
            value = int(self._cfg.get("width") or WIDGET_MIN_WIDTH_HORIZONTAL)
        except (TypeError, ValueError):
            value = WIDGET_MIN_WIDTH_HORIZONTAL
        return min(WIDGET_MAX_WIDTH_HORIZONTAL, max(WIDGET_MIN_WIDTH_HORIZONTAL, value))

    def _cfg_orientation(self) -> str:
        value = self._cfg.get("orientation")
        if value in (ORIENTATION_VERTICAL, ORIENTATION_HORIZONTAL):
            return value
        return ORIENTATION_VERTICAL

    def _on_top(self) -> bool:
        return self._force_on_top or bool(self._cfg.get("always_on_top", False))

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
        self._left_col.setFixedWidth(WIDGET_WIDTH - CONTENT_MARGIN_H * 2)
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
        self.name_label = QLabel()
        self.name_label.setToolTip("더블클릭하여 이름 수정")
        self.name_label.installEventFilter(self)

        self.name_edit = _NameEdit()
        self.name_edit.setMaxLength(USER_NAME_MAX_LEN)
        self.name_edit.setPlaceholderText("이름")
        self.name_edit.hide()
        self.name_edit.returnPressed.connect(self._commit_name_edit)
        self.name_edit.focus_lost.connect(self._commit_name_edit)
        self.name_edit.escaped.connect(self._finish_name_edit)

        header.addWidget(self.status_dot)
        header.addWidget(self.name_label, 1)
        header.addWidget(self.name_edit, 1)
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

        # ---- 업무명 배지: 등록한 Task 강조 (비어 있으면 숨김 / 클릭 없음) ----
        self.task_title_label = QLabel()
        self.task_title_label.setTextFormat(Qt.PlainText)
        self.task_title_label.setAlignment(Qt.AlignCenter)
        self.task_title_label.hide()
        controls.addWidget(self.task_title_label)

        # ---- Task 등록 / 완료 버튼 ----
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_task = QPushButton("Task 등록")
        self.btn_task_clear = QPushButton("Task 완료")
        for btn in (self.btn_task, self.btn_task_clear):
            btn.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(btn)
        self.btn_task.clicked.connect(self.task_register_requested.emit)
        self.btn_task_clear.clicked.connect(self.task_clear_requested.emit)
        controls.addLayout(buttons)

        # ---- 투명도 슬라이더 (슬라이더 값 = 투명도 % = 100 - 불투명도 %) ----
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(8)
        self.opacity_caption = QLabel("투명도")

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, TRANSPARENCY_MAX)
        self.opacity_slider.setValue(round((1 - self._cfg_opacity()) * 100))
        self.opacity_slider.setCursor(Qt.PointingHandCursor)

        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_slider.sliderReleased.connect(self._save_opacity)

        opacity_row.addWidget(self.opacity_caption)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        controls.addLayout(opacity_row)

        self._left_layout.addWidget(info_box)
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
        self.todo_panel = TodoPanel(lambda: snippets.from_config(self._cfg))

        self.apply_task(None)

    def apply_appearance(self):
        """현재 테마(theme.current())로 색 / 글꼴을 다시 입힌다. 글자 크기는 좌패널 배율을 따른다."""
        t = theme.current()
        s = t.left_scale
        sub_style = f"font-size: {px(11, s)}px; color: {t.text_sub};"
        # WA_TranslucentBackground 사용 시 자식 위젯이 배경을 불투명하게 덮으므로
        # QLabel 배경을 반드시 transparent 로 강제해야 한다.
        self.setStyleSheet(
            theme.button_style(t, px(12, s))
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {t.overlay(50)};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {t.overlay(120)};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                margin: -5px 0;
                background: {t.text_main};
                border-radius: 6px;
            }}
            """
        )
        self.name_edit.setStyleSheet(
            f"""
            QLineEdit {{
                {self._name_font()}
                background: {t.overlay(18)};
                color: {t.text_main};
                font-family: {t.font_family};
                border: 1px solid {t.overlay(90)};
                border-radius: 4px;
                padding: 0px 4px;
                selection-background-color: {t.accent};
                selection-color: {t.on_accent};
            }}
            """
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
            background: {t.accent_rgba(40)};
            border: 1px solid {t.accent_rgba(170)};
            border-radius: 6px;
            padding: 5px 8px;
            """
        )
        self.opacity_caption.setStyleSheet(sub_style)
        self.opacity_value.setStyleSheet(sub_style)
        self.opacity_value.setFixedWidth(px(34, s))
        for line in self._separators:
            line.setStyleSheet(f"background: {t.line}; border: none;")
        self.todo_panel.apply_appearance()

        self.set_user_name(self._cfg.get("user_name", ""))
        self._set_remaining_style(warn=self.remaining_label.text().startswith("+"))
        self._apply_task_dot(self.btn_task_clear.isEnabled())
        if self._task_title:
            self._set_task_title(self._task_title)
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
        """세로: info / TODO / controls 를 한 줄로
        가로: 좌측은 TODO 추가 전 위젯 그대로(info / 여백 / controls), 우측에 TODO"""
        if orientation == self._orientation:
            return

        # 좌측 칼럼의 index 1 자리(info 와 controls 사이)를 비운다
        if self._orientation == ORIENTATION_HORIZONTAL:
            self._right_layout.removeWidget(self.todo_panel)
            self._left_layout.takeAt(1)  # 여백(stretch)
        elif self._orientation == ORIENTATION_VERTICAL:
            self._left_layout.removeWidget(self.todo_panel)

        horizontal = orientation == ORIENTATION_HORIZONTAL
        if horizontal:
            self._right_layout.addWidget(self.todo_panel)
            self._left_layout.insertStretch(1, 1)
        else:
            self._left_layout.insertWidget(1, self.todo_panel, 1)
        self.todo_panel.show()  # 다른 부모로 옮기면 숨김 상태가 되므로

        # 숨긴 위젯은 레이아웃에서 자리/간격을 차지하지 않는다
        self._col_separator.setVisible(horizontal)
        self._right_col.setVisible(horizontal)

        self._orientation = orientation
        self._apply_size_limits()
        self._grip.set_vertical(not horizontal)
        self._place_grip()

    def _apply_size_limits(self):
        """세로: 폭 고정 / 높이 조절, 가로: 높이 고정 / 폭 조절"""
        min_height = self._min_height()
        # 이전 모드의 min/max 와 엇갈리지 않도록 범위를 먼저 풀고 다시 건다
        self.setMinimumSize(0, 0)
        if self._orientation == ORIENTATION_HORIZONTAL:
            self.setMaximumSize(WIDGET_MAX_WIDTH_HORIZONTAL, min_height)
            self.setMinimumSize(WIDGET_MIN_WIDTH_HORIZONTAL, min_height)
            self.resize(self._cfg_width(), min_height)
        else:
            self.setMaximumSize(WIDGET_WIDTH, max(WIDGET_MAX_HEIGHT, min_height))
            self.setMinimumSize(WIDGET_WIDTH, min_height)
            self.resize(WIDGET_WIDTH, self._cfg_height())

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
        """슬라이더의 불투명도 (슬라이더 값은 투명도 %)"""
        return 1 - self.opacity_slider.value() / 100

    def _apply_opacity(self):
        """글자도 함께 투명(Appearance fade_text): 창 전체 불투명도
        해제(기본): 창은 불투명하게 두고 paintEvent 가 배경만 반투명하게 칠한다"""
        fade_text = theme.current().fade_text
        self.setWindowOpacity(self._opacity() if fade_text else 1.0)
        self.update()

    def _on_opacity_changed(self, transparency: int):
        self._apply_opacity()
        self.opacity_value.setText(f"{transparency}%")
        # 드래그 중에는 저장하지 않고(sliderReleased 에서 저장), 키보드/클릭 조작만 즉시 저장
        if not self.opacity_slider.isSliderDown():
            self._save_opacity()

    def _save_opacity(self):
        # 설정에는 기존 호환을 위해 불투명도로 저장 (부동소수 오차 방지 round)
        self._cfg["opacity"] = round(1 - self.opacity_slider.value() / 100, 2)
        widget_config.save_config(self._cfg)

    def save_size(self):
        """조절한 크기 저장 - 세로 모드는 높이, 가로 모드는 폭"""
        if self._orientation == ORIENTATION_HORIZONTAL:
            self._cfg["width"] = self.width()
        else:
            self._cfg["height"] = self.height()
        widget_config.save_config(self._cfg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_grip()

    def _place_grip(self):
        if self._orientation == ORIENTATION_HORIZONTAL:
            self._grip.setGeometry(
                self.width() - RESIZE_MARGIN,
                CORNER_RADIUS,
                RESIZE_MARGIN,
                self.height() - CORNER_RADIUS * 2,
            )
        else:
            self._grip.setGeometry(
                CORNER_RADIUS,
                self.height() - RESIZE_MARGIN,
                self.width() - CORNER_RADIUS * 2,
                RESIZE_MARGIN,
            )
        self._grip.raise_()

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
        if registered:
            style = f"background: {TASK_DOT_COLOR}; border-radius: 6px;"
        else:
            style = (
                f"background: transparent; border: 1.5px solid {theme.current().text_sub};"
                " border-radius: 6px;"
            )
        self.status_dot.setStyleSheet(style)

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
        else:
            self.in_label.setText(f"시작 {task.start_at:%H:%M}")
            self.out_label.setText(f"종료 {task.end_at:%H:%M}")
            self._set_task_title(task.title)
        self.btn_task_clear.setEnabled(task is not None)
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

    def set_user_name(self, name: str):
        if name:
            self.name_label.setText(name)
            self.name_label.setStyleSheet(self._name_font())
        else:
            self.name_label.setText("이름")
            self.name_label.setStyleSheet(
                f"{self._name_font()} color: {theme.current().text_dim};"
            )

    # ==================================================
    # 사용자 이름 편집 (더블클릭)
    # ==================================================
    def eventFilter(self, obj, event):
        if obj is self.name_label and event.type() == QEvent.MouseButtonDblClick:
            self.start_name_edit()
            return True
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

        handlers = {
            "task_register": self.task_register_requested.emit,
            "task_clear": self._on_clear_shortcut,
            "todo_focus": self.todo_panel.focus_input,
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

    def _on_clear_shortcut(self):
        if self.btn_task_clear.isEnabled():
            self.task_clear_requested.emit()

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
        menu = QMenu(self)
        menu.setStyleSheet(theme.menu_style(theme.current()))

        act_clear = menu.addAction("완료 항목 정리", self.todo_panel.clear_done)
        act_clear.setEnabled(self.todo_panel.has_done())
        export_menu = menu.addMenu("TODO 내보내기")
        export_menu.setStyleSheet(menu.styleSheet())
        act_active = export_menu.addAction(
            "화면 목록…", lambda: self._export_todos(archived=False)
        )
        act_active.setEnabled(bool(self.todo_panel.items()))
        act_archived = export_menu.addAction(
            "보관 항목 전체…", lambda: self._export_todos(archived=True)
        )
        act_archived.setEnabled(bool(todo_store.load_archived()))
        menu.addSeparator()

        if self._orientation == ORIENTATION_HORIZONTAL:
            menu.addAction(
                "세로 모드", lambda: self.set_orientation(ORIENTATION_VERTICAL)
            )
        else:
            menu.addAction(
                "가로 모드", lambda: self.set_orientation(ORIENTATION_HORIZONTAL)
            )

        act_lock = menu.addAction("위치/크기 잠금")
        act_lock.setCheckable(True)
        act_lock.setChecked(self._locked)
        act_lock.toggled.connect(self.set_locked)

        act_auto = menu.addAction("윈도우 시작 시 실행")
        act_auto.setCheckable(True)
        act_auto.setChecked(os_win.is_autostart_enabled())
        act_auto.toggled.connect(self._on_autostart_toggled)

        # act_top = menu.addAction("항상 위에 보이기")
        # act_top.setCheckable(True)
        # act_top.setChecked(bool(self._cfg.get("always_on_top", False)))
        # act_top.toggled.connect(self.set_always_on_top)

        menu.addAction("설정", self.settings_requested.emit)
        menu.addAction("위젯 숨기기", self.hide_widget)
        menu.addSeparator()
        menu.addAction("종료", self.quit_requested.emit)

        menu.exec(event.globalPos())

    def _export_todos(self, archived: bool):
        """TODO 를 Markdown 체크리스트 파일로 저장한다. 마지막 저장 폴더를 기억한다."""
        now = datetime.now()
        if archived:
            text = todo_export.archived_to_markdown(todo_store.load_archived(), now)
        else:
            text = todo_export.to_markdown(self.todo_panel.items(), now)

        folder = self._cfg.get("export_dir") or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "TODO 내보내기",
            os.path.normpath(
                os.path.join(folder, todo_export.default_filename(archived, now))
            ),
            "Markdown (*.md)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            QMessageBox.warning(self, "TODO 내보내기", f"파일을 저장하지 못했습니다.\n{e}")
            return
        self._cfg["export_dir"] = os.path.dirname(path)
        widget_config.save_config(self._cfg)

    def set_locked(self, locked: bool):
        self._locked = locked
        self._grip.set_enabled(not locked)
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

        # setWindowFlags 는 창을 숨기므로 표시 중이었다면 다시 보여준다
        was_visible = self.isVisible()
        pos = self.pos()
        self._apply_window_flags()
        self.move(pos)
        if was_visible:
            self.show()
            self._apply_z_order()

    def _on_autostart_toggled(self, enable: bool):
        if not os_win.set_autostart(enable):
            # 실패 시 체크 상태를 원복(다음 메뉴 오픈 시 레지스트리 값 기준으로 재구성됨)
            print("자동 실행 설정을 변경하지 못했습니다.")

    # ==================================================
    # 리마인더
    # ==================================================
    def check_reminders(self):
        """시각이 된 리마인더를 팝업 + reminder_due 시그널로 알린다."""
        now = datetime.now().astimezone()
        for item in self.todo_panel.pop_due(now):
            text = todo_store.strip_reminder(item["text"])
            self._show_reminder_popup(item["id"], text, todo_store.due_at(item))
            self.reminder_due.emit(item["id"], text)
        self.todo_panel.refresh_rows()  # 지난 리마인더 색 갱신

    def _show_reminder_popup(self, item_id: str, text: str, due: datetime):
        popup = ReminderPopup(item_id, text, due)
        popup.done_requested.connect(lambda _id: self.todo_panel.set_done(_id, True))
        popup.snooze_requested.connect(self.todo_panel.snooze)
        popup.destroyed.connect(lambda _=None, p=popup: self._popups.remove(p))
        popup.move(self._popup_position(popup))
        self._popups.append(popup)
        popup.show()

    def _popup_position(self, popup: QWidget) -> QPoint:
        """위젯 위치와 상관없이 주 모니터 우측 상단부터 아래로 쌓고,
        아래 공간이 없으면 왼쪽 열로 넘어가 다시 위에서부터 쌓는다. (팝업 폭은 고정)"""
        area = QApplication.primaryScreen().availableGeometry()
        top = area.top() + SCREEN_MARGIN
        bottom = area.bottom() + 1 - SCREEN_MARGIN
        right = area.right() + 1 - SCREEN_MARGIN

        # 이미 떠 있는 팝업들을 같은 규칙으로 배치해 본 다음 칸이 새 팝업 자리
        y = top
        for p in self._popups + [popup]:
            if y > top and y + p.height() > bottom:
                right -= p.width() + POPUP_GAP
                y = top
            pos = QPoint(max(right - p.width(), area.left()), y)
            y += p.height() + POPUP_GAP
        return pos

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

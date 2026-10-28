"""위젯 안의 TODO 리스트

- 목록 아래 입력창에서 Enter 로 바로 추가 (별도 창 없음)
- 입력 중 `(@` 를 치면 리마인더 피커가 떠서 `(@YYYY-MM-DD HH:mm)` 토큰을 넣는다
- 입력 중 `:idea:` 같은 스니펫 트리거를 치면 설정한 문구(💡)로 바뀐다 (설정창 Snippets 탭)
- 체크하면 취소선 + 목록 아래로, 우클릭 메뉴 "완료 항목 정리" 로 일괄 보관(DB 에는 남음)
- 더블클릭으로 그 자리에서 수정 (Enter/포커스 이동: 저장, Esc: 취소)
- 클릭으로 선택 (Ctrl: 하나씩 추가/빼기, Shift: 범위). 빈 곳 클릭 / Esc 로 해제.
  선택 테두리는 목록(container)이 그린다 - 화면에서 이어진 선택 행끼리는 테두리 하나로 묶는다.
  선택한 채로 입력하면 마지막으로 클릭한 항목의 하위로 들어간다.
- 드래그로 순서/레벨 변경: 행 가운데에 놓으면 그 항목의 하위로, 행 사이에 놓으면 그 자리로.
  선택한 행을 끌면 선택 항목이 모두 함께 옮겨진다.
  (계층 규칙은 manager/todo_tree 참고 - 상위를 완료하면 하위도 완료, 상위를 지우면 하위는 한 단계 위로)
- 우클릭 메뉴: 검색 / 완료 항목 정리 / 내보내기 / 추가 / 삭제 / 태그(체크박스 왼쪽 색 막대)
  여러 개를 선택한 채 우클릭하면 선택 항목 전체에 적용된다.
  태그는 기본 6색 + 사용자 태그(config.json custom_tags, "+ 태그 추가…" / 설정창에서 관리)
- 형제끼리는 미완료 -> 완료 순, 리마인더 항목이 시각순으로 위에 고정되고 나머지는 사용자가 정한 순서
- Ctrl+F / 우클릭 "검색": 목록 위에 [전체][오늘][지연][예정] 칩 + 검색칸 줄이 열린다 (manager/todo_filter).
  맞는 항목의 상위는 흐리게 함께 보인다. 거르는 중에는 드래그하지 않고, 할 일을 추가하면 전체 보기로 돌아간다.
  Esc: 검색어를 지우고, 비어 있으면 줄을 닫는다 (닫으면 필터도 풀림)
  검색어가 바뀔 때마다 맞는 글자를 노랗게 칠했다가 2초 뒤 서서히 지운다 (상위 문맥 행은 칠하지 않음)

드래그는 QDrag(Windows OLE DoDragDrop)를 쓰지 않고 행의 마우스 grab 으로 직접 처리한다.
OLE 드래그 루프 동안에는 휠이 오지 않고, 커서를 움직일 때만 자동 스크롤되기 때문이다.
"""

from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from manager import todo_filter, todo_store, todo_tree
from ui import theme
from ui.reminder_picker import ReminderPicker
from ui.tag_dialog import TagDialog
from ui.text_input import PreeditLineEdit, expand_snippet_later, py_cursor, utf16_pos
from ui.theme import px


TRIGGER = "(@"
ROW_HOVER_ALPHA = 24  # 마우스를 올린 행 배경 (테마의 덧칠 색)
ROW_RADIUS = 4
SELECTED_BORDER = 2.0  # 선택한 행(이어진 행은 묶어서)의 강조색 테두리 두께(px)
TAG_CHECKED_BORDER = 1  # 태그 메뉴: 선택 항목들의 지금 태그를 감싸는 강조색 테두리(px)
DROP_BOX_BORDER = 2  # 드래그 중 하위로 들어갈 행 테두리(px)
DROP_LINE_WIDTH = 3  # 드래그 중 행 사이에 놓일 자리 표시선(px)
AUTO_SCROLL_MARGIN = (
    24  # 드래그 중 목록 위/아래 끝(과 그 바깥)에서 자동 스크롤되는 영역(px)
)
AUTO_SCROLL_MS = 30  # 자동 스크롤 주기 - 커서를 멈춰 두어도 계속 스크롤된다
AUTO_SCROLL_MAX_STEP = 20  # 끝에서 멀리 벗어날수록 빠르게, 한 번에 최대 이만큼(px)
DRAG_GHOST_OPACITY = 0.8  # 끌고 가는 행 그림
INDENT_STEP = 16  # 레벨 하나당 들여쓰기(px) - 체크박스 + 간격
MAX_INDENT_DEPTH = 3  # 위젯 폭이 좁으므로 이보다 깊은 레벨은 같은 들여쓰기로 표시
# 본문(12px) 크기의 컬러 이모지는 테두리가 뭉개지므로 행에서는 조금 크게 그린다
EMOJI_PX = 14
TAG_BAR_WIDTH = 3  # 체크박스 왼쪽 태그 막대 (태그가 없어도 자리는 둔다)
TOGGLE_SIZE = 14  # 하위 접기/펼치기 ▸/▾ 버튼 (하위가 없어도 자리는 둔다)
TAG_BAR_GAP = 3  # 태그 막대 - 체크박스 간격 (체크박스 - 글자 간격보다 가깝게)
TAG_ICON_PX = 12
# 태그 (메뉴 이름, 색) - 키는 todo_store.TAGS 와 같다
TAG_COLORS = {
    "red": ("Red", "#ec5f5d"),
    "orange": ("Orange", "#f39a39"),
    "yellow": ("Yellow", "#f5cc45"),
    "green": ("Green", "#61c454"),
    "blue": ("Blue", "#3e8ef7"),
    "gray": ("Gray", "#98989d"),
}
PLACEHOLDER = "+ 할 일 추가 · (@ 리마인더"
PLACEHOLDER_CHILD = "+ 하위 할 일 추가 · Esc 선택 해제"
SEARCH_PLACEHOLDER = "🔍 검색 · Esc 닫기"
EMPTY_TEXT = "할 일이 없습니다"
EMPTY_FILTERED_TEXT = "일치하는 할 일이 없습니다"
# 검색 줄의 날짜별 보기 칩 - 키는 todo_filter.VIEWS 와 같다
VIEW_LABELS = {"all": "전체", "today": "오늘", "overdue": "지연", "upcoming": "예정"}
# 검색 하이라이트: 검색어가 바뀌면 맞는 글자 배경을 칠해 두었다가 서서히 지운다
HIGHLIGHT_COLOR = "#f5cc45"  # 태그 Yellow 와 같은 색
HIGHLIGHT_ALPHA = 150  # 가장 진할 때의 불투명도 (0~255)
HIGHLIGHT_HOLD_MS = 2000
HIGHLIGHT_FADE_MS = 600


def _indent(depth: int) -> int:
    return min(depth, MAX_INDENT_DEPTH) * INDENT_STEP


def _tag_icon(color: str, outline: str = "") -> QIcon:
    """메뉴용 색 점. outline 을 주면 속이 빈 원 (태그 없음)"""
    ratio = 2  # 고해상도 화면에서도 매끄럽게
    pixmap = QPixmap(TAG_ICON_PX * ratio, TAG_ICON_PX * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(1, 1, TAG_ICON_PX - 2, TAG_ICON_PX - 2)
    if outline:
        painter.setPen(QPen(QColor(outline), 1.2))
        painter.drawEllipse(rect)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(rect)
    painter.end()
    return QIcon(pixmap)


def _panel_style(t: theme.Theme) -> str:
    s = t.todo_scale
    return f"""
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {t.overlay(50)};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QLineEdit {{
        background: {t.overlay(18)};
        color: {t.todo_color};
        font-family: {t.font_family};
        font-size: {px(12, s)}px;
        border: 1px solid {t.overlay(30)};
        border-radius: 6px;
        padding: 3px 6px;
        selection-background-color: {t.accent};
        selection-color: {t.on_accent};
    }}
    QLineEdit:focus {{ border: 1px solid {t.overlay(90)}; }}
    QCheckBox {{ background: transparent; spacing: 0px; }}
    QCheckBox::indicator {{
        width: {px(12, s)}px;
        height: {px(12, s)}px;
        border: 1px solid {t.overlay(130)};
        border-radius: 3px;
        background: transparent;
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {t.text_main}; }}
    QCheckBox::indicator:checked {{
        background: {t.accent};
        border: 1px solid {t.accent};
    }}
    QPushButton#delete {{
        background: transparent;
        color: {t.text_sub};
        border: none;
        padding: 0px;
        font-size: {px(11, s)}px;
    }}
    QPushButton#delete:hover {{ color: {t.text_warn}; }}
    QPushButton#toggle {{
        background: transparent;
        color: {t.text_sub};
        border: none;
        padding: 0px;
        font-size: {px(11, s)}px;
    }}
    QPushButton#toggle:hover {{ color: {t.accent}; }}
    QPushButton#chip {{
        background: transparent;
        font-family: {t.font_family};
        font-size: {px(11, s)}px;
        border: 1px solid transparent;
        padding: 2px 8px;
    }}
"""


class TodoInput(QLineEdit):
    """`(@` 를 감지해 리마인더 피커를 띄우고, 스니펫 트리거를 문구로 바꾸는 입력창"""

    escaped = Signal()
    focus_lost = Signal()

    def __init__(self, reminders_provider, snippets_provider, parent=None):
        """reminders_provider: () -> [(datetime, 본문)]  (피커에 보여줄 기존 리마인더)
        snippets_provider: () -> {트리거: 문구}"""
        super().__init__(parent)
        self._reminders_provider = reminders_provider
        self._snippets_provider = snippets_provider
        self._picker = None
        self._trigger_pos = 0
        self.textEdited.connect(self._on_text_edited)

    @property
    def picker_open(self) -> bool:
        return self._picker is not None

    def _on_text_edited(self, text: str):
        pos = py_cursor(self)
        if pos >= len(TRIGGER) and text[pos - len(TRIGGER) : pos] == TRIGGER:
            self.open_picker(pos)
        else:
            expand_snippet_later(self, self._snippets_provider)

    def open_picker(self, trigger_pos: int):
        self._trigger_pos = trigger_pos
        text = self.text()
        # 이미 토큰이 있으면(수정 중) 그 시각으로 시작
        existing = todo_store.parse_reminder(
            text[: trigger_pos - len(TRIGGER)] + text[trigger_pos:]
        )
        self._picker = ReminderPicker(existing, self._reminders_provider(), self)
        self._picker.picked.connect(self._insert_token)
        self._picker.closed.connect(self._on_picker_closed)
        self._picker.popup_for(self)

    def _insert_token(self, dt: datetime):
        text = self.text()
        # 토큰은 항목당 하나만 - 기존 토큰은 지우고 `(@` 자리에 새 토큰을 넣는다
        left = todo_store.REMINDER_RE.sub("", text[: self._trigger_pos - len(TRIGGER)])
        right = todo_store.REMINDER_RE.sub("", text[self._trigger_pos :])
        token = todo_store.format_token(dt)
        if right and not right.startswith(" "):
            token += " "
        self.setText(left + token + right)
        self.setCursorPosition(utf16_pos(self.text(), len(left) + len(token)))

    def _on_picker_closed(self):
        self._picker = None
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # 피커로 포커스가 넘어간 경우는 수정 중으로 본다
        if not self.picker_open:
            self.focus_lost.emit()


class _SearchEdit(PreeditLineEdit):
    """검색칸. Esc 는 FilterBar 가 처리한다."""

    escaped = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)


class _Chip(QPushButton):
    """검색 줄의 보기 칩 (알약 모양). 스타일시트의 border-radius 는 안티앨리어싱 없이 그려져
    둥근 끝이 계단처럼 깨지므로 직접 그린다. 크기(글자 / 여백)만 스타일시트(QPushButton#chip)를 따른다."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, event):
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 1px 선이 픽셀 경계에 걸쳐 흐려지지 않도록 반 픽셀 안쪽에 그린다
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        hover = self.underMouse()
        if self.isChecked():
            painter.setPen(QPen(QColor(t.accent), 1))
            painter.setBrush(QColor(t.accent))
            text_color = t.on_accent
        else:
            painter.setPen(QPen(t.overlay_color(90 if hover else 40), 1))
            painter.setBrush(Qt.NoBrush)
            text_color = t.text_main if hover else t.text_sub
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QColor(text_color))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


class FilterBar(QWidget):
    """Ctrl+F / 우클릭 "검색" 으로 여는 줄: 날짜별 보기 칩 + 검색칸.
    한글은 조합 중인 글자까지 바로 걸러지도록 preedit 이 바뀔 때도 changed 를 보낸다."""

    changed = Signal()  # 보기 / 검색어가 바뀜
    close_requested = Signal()  # ✕ / 빈 검색칸에서 Esc

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 4, 0)
        root.setSpacing(4)

        chips = QHBoxLayout()
        chips.setSpacing(4)
        self._group = QButtonGroup(self)
        self._chips = {}
        for view in todo_filter.VIEWS:
            chip = _Chip(VIEW_LABELS[view])
            self._group.addButton(chip)
            self._chips[view] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        self._chips["all"].setChecked(True)
        self._group.buttonClicked.connect(lambda _button: self.changed.emit())
        root.addLayout(chips)

        search = QHBoxLayout()
        search.setSpacing(4)
        self.edit = _SearchEdit()
        self.edit.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.edit.textChanged.connect(lambda _text: self.changed.emit())
        self.edit.preedit_changed.connect(self.changed.emit)
        self.edit.escaped.connect(self._on_escaped)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("delete")
        btn_close.setFixedSize(16, 16)
        btn_close.setFocusPolicy(Qt.NoFocus)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("검색 닫기")
        btn_close.clicked.connect(self.close_requested.emit)
        search.addWidget(self.edit, 1)
        search.addWidget(btn_close)
        root.addLayout(search)

    def view(self) -> str:
        return next(view for view, chip in self._chips.items() if chip.isChecked())

    def query(self) -> str:
        return self.edit.full_text()

    def set_counts(self, counts: dict):
        """칩 글자에 개수 표시 ("오늘 2", 0 이면 이름만)"""
        for view, n in counts.items():
            label = VIEW_LABELS[view]
            self._chips[view].setText(f"{label} {n}" if n else label)

    def reset(self):
        """전체 보기 + 빈 검색어 (changed 는 보내지 않는다)"""
        self.blockSignals(True)
        self._chips["all"].setChecked(True)
        self.edit.clear()
        self.blockSignals(False)

    def _on_escaped(self):
        if self.edit.text():
            self.edit.clear()
        else:
            self.close_requested.emit()


class TodoRow(QWidget):
    toggled = Signal(str, bool)
    deleted = Signal(str)
    edited = Signal(str, str)
    collapse_toggled = Signal(str)
    clicked = Signal(
        object, object
    )  # TodoRow, Qt.KeyboardModifiers (드래그 없이 눌렀다 뗌)
    # 드래그: 시작 후의 이동 / 놓음 / Esc 취소는 이 행의 마우스 grab 으로 받아 패널에 넘긴다
    drag_started = Signal(object)  # TodoRow
    drag_moved = Signal()
    drag_released = Signal()
    drag_canceled = Signal()

    def __init__(self, reminders_provider, snippets_provider, tag_color, parent=None):
        """위젯만 만든다. 보여줄 항목은 set_state 로 정한다 (목록을 다시 만들 때 행을 재사용한다).
        tag_color: (태그 키) -> "#rrggbb" / None (태그 없음 또는 지워진 사용자 태그)"""
        super().__init__(parent)
        self.item = None
        self.depth = 0  # 레벨 (최상위 0)
        self.context = False
        self.mark_query = ""  # 검색 하이라이트할 검색어 (TodoPanel 이 정함)
        self.mark_level = 0.0  # 하이라이트 진하기 0~1 (0 이면 칠하지 않음)
        self._tag_color = tag_color
        # 태그 막대에 마지막으로 칠한 색 (바뀔 때만 스타일시트를 다시 건다)
        self._bar_color = ""
        self._editing = False
        self._hover = False
        self._press_pos = None  # 드래그 시작 판정용 누른 지점
        self._dragging = False

        layout = QHBoxLayout(self)
        layout.setSpacing(6)  # 여백은 레벨에 따라 set_state 가 정한다
        self._layout = layout

        # 자식 위젯은 모두 이 행을 부모로 만든다 - 부모 없이 setVisible(True) 하면
        # 레이아웃에 들어가기 전까지 최상위 창으로 떠서 화면 가운데가 깜빡인다 (그리고 느리다)
        # 접기/펼치기 버튼. 하위가 없어도 자리는 비워 둬서 체크박스 위치를 맞춘다
        self.btn_toggle = QPushButton(self)
        self.btn_toggle.setObjectName("toggle")
        self.btn_toggle.setFixedSize(TOGGLE_SIZE, TOGGLE_SIZE)
        self.btn_toggle.setFocusPolicy(Qt.NoFocus)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.clicked.connect(
            lambda: self.collapse_toggled.emit(self.item["id"])
        )
        policy = self.btn_toggle.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.btn_toggle.setSizePolicy(policy)

        # 태그 막대 (행 높이만큼) + 체크박스. 태그가 없어도 막대 자리는 비워 둔다
        self.tag_bar = QFrame(self)
        self.tag_bar.setFixedWidth(TAG_BAR_WIDTH)
        lead = QHBoxLayout()
        lead.setSpacing(TAG_BAR_GAP)

        self.check = QCheckBox(self)
        self.check.setCursor(Qt.PointingHandCursor)
        self.check.setFocusPolicy(Qt.NoFocus)
        self.check.toggled.connect(lambda on: self.toggled.emit(self.item["id"], on))
        lead.addWidget(self.btn_toggle, 0, Qt.AlignTop)
        lead.addWidget(self.tag_bar)
        lead.addWidget(self.check, 0, Qt.AlignTop)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.RichText)
        # RichText 라벨은 기본값(링크 클릭)이면 마우스 이동을 삼켜서 행의 드래그가 시작되지 않는다
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label.setToolTip("클릭하여 선택 · 더블클릭하여 수정 · 드래그하여 이동")
        self.label.installEventFilter(self)

        self.editor = TodoInput(reminders_provider, snippets_provider, self)
        self.editor.hide()
        self.editor.returnPressed.connect(self._commit_edit)
        self.editor.focus_lost.connect(self._commit_edit)
        self.editor.escaped.connect(self._cancel_edit)

        self.btn_delete = QPushButton("✕", self)
        self.btn_delete.setObjectName("delete")
        self.btn_delete.setFixedSize(16, 16)
        self.btn_delete.setFocusPolicy(Qt.NoFocus)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setToolTip("삭제")
        self.btn_delete.clicked.connect(lambda: self.deleted.emit(self.item["id"]))
        # hover 할 때만 보이되, 숨겨도 자리는 유지해서 줄바꿈이 흔들리지 않게
        policy = self.btn_delete.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.btn_delete.setSizePolicy(policy)
        self.btn_delete.hide()

        layout.addLayout(lead)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.btn_delete, 0, Qt.AlignTop)

    def set_state(self, item: dict, depth: int, context=False, has_children=False):
        """보여줄 항목과 자리를 (다시) 정하고 그린다.
        context: 검색 / 날짜별 보기에는 맞지 않지만 맞는 항목의 상위라서 보이는 행 (흐리게)
        has_children: 하위가 있으면 ▸/▾ 접기 버튼을 보인다 (item["collapsed"] 가 방향을 정함)"""
        self.item = item
        self.depth = depth
        self.context = context
        # 좌우 여백은 hover 배경이 체크박스/삭제 버튼에 붙지 않게
        self._layout.setContentsMargins(4 + self.indent(), 2, 4, 2)
        self.btn_toggle.setVisible(has_children)
        # 표시만 맞춘다 - toggled 가 다시 완료 처리를 부르지 않게
        self.check.blockSignals(True)
        self.check.setChecked(item["done"])
        self.check.blockSignals(False)
        self.render()

    def indent(self) -> int:
        """레벨에 따른 왼쪽 들여쓰기(px)"""
        return _indent(self.depth)

    def render(self, now: datetime = None):
        now = now or datetime.now().astimezone()
        t = theme.current()
        s = t.todo_scale
        done = self.item["done"]
        tag_color = self._tag_color(self.item.get("tag"))
        collapsed = self.item.get("collapsed")
        self.btn_toggle.setText("▸" if collapsed else "▾")
        self.btn_toggle.setToolTip("하위 펼치기" if collapsed else "하위 접기")
        if tag_color != self._bar_color:
            self._bar_color = tag_color
            self.tag_bar.setStyleSheet(
                f"background: {tag_color or 'transparent'}; border: none;"
                f" border-radius: {TAG_BAR_WIDTH // 2}px;"
            )
        emoji_style = f"font-size:{px(EMOJI_PX, s)}px;"
        marks, mark_style = (), ""
        if self.mark_level > 0 and not self.context:
            marks = todo_filter.match_spans(
                todo_store.strip_reminder(self.item["text"]), self.mark_query
            )
            mark = QColor(HIGHLIGHT_COLOR)
            mark.setAlpha(round(HIGHLIGHT_ALPHA * self.mark_level))
            mark_style = f"background-color:{mark.name(QColor.HexArgb)};"
        body = (
            todo_store.to_html(self.item["text"], emoji_style, marks, mark_style)
            or "&nbsp;"
        )
        color = t.text_sub if done or self.context else t.todo_color
        html = f'<span style="color:{color};">{body}</span>'
        if done:
            html = f"<s>{html}</s>"

        due = todo_store.due_at(self.item)
        if due is not None:
            chip_color = t.text_warn if (not done and due <= now) else t.text_sub
            html += (
                f'&nbsp;<span style="color:{chip_color}; font-size:{px(11, s)}px;">'
                f"⏰&nbsp;{due:%m/%d %H:%M}</span>"
            )
        self.label.setText(
            f'<div style="font-family:{t.font_family}; font-size:{px(12, s)}px;">'
            f"{html}</div>"
        )

    # ---- 수정 ----
    def start_edit(self):
        self._editing = True
        self.label.hide()
        self.editor.setText(self.item["text"])
        self.editor.show()
        self.editor.setFocus()
        self.editor.end(False)

    def _commit_edit(self):
        if not self._editing:
            return
        self._finish_edit()
        text = self.editor.text().strip()
        if text and text != self.item["text"]:
            self.edited.emit(self.item["id"], text)

    def _cancel_edit(self):
        if self._editing:
            self._finish_edit()

    def _finish_edit(self):
        self._editing = False
        if self.editor.hasFocus():
            # 포커스를 가진 편집칸을 숨기면 Qt 가 포커스를 다음 위젯으로 넘기며 목록을 그쪽으로
            # 스크롤한다 (맨 위로 튀기도 함). 먼저 목록(부모 container)으로 돌려 둔다
            self.parentWidget().setFocus(Qt.OtherFocusReason)
        self.editor.hide()
        self.label.show()

    # ---- 이벤트 ----
    def eventFilter(self, obj, event):
        if obj is self.label and event.type() == QEvent.MouseButtonDblClick:
            self.start_edit()
            return True
        return super().eventFilter(obj, event)

    # 행의 누름은 선택 / 드래그용으로 받아서 위젯 창 이동으로 넘어가지 않게 한다
    def mousePressEvent(self, event):
        if not self._editing and event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.drag_moved.emit()
            return
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= QApplication.startDragDistance():
                self._press_pos = None
                self._dragging = True
                self.grabKeyboard()  # Esc 로 취소
                self.drag_started.emit(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._stop_drag()
            self.drag_released.emit()
            return
        if self._press_pos is not None and event.button() == Qt.LeftButton:
            self._press_pos = None
            self.clicked.emit(self, event.modifiers())
            return
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._dragging and event.key() == Qt.Key_Escape:
            self._stop_drag()
            self.drag_canceled.emit()
            return
        super().keyPressEvent(event)

    def _stop_drag(self):
        self._dragging = False
        self.releaseKeyboard()

    def enterEvent(self, event):
        self._hover = True
        self.btn_delete.show()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.btn_delete.hide()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        # 선택 테두리는 TodoPanel._paint_selection 이 목록 위에 그린다 (이어진 행을 묶기 위해)
        if not self._hover:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect().adjusted(self.indent(), 0, 0, 0)), ROW_RADIUS, ROW_RADIUS
        )
        painter.fillPath(path, theme.current().overlay_color(ROW_HOVER_ALPHA))


class TodoPanel(QWidget):
    """TODO 목록 + 입력창. 상태는 todo_store 로 바로바로 저장한다. (선택 상태는 저장하지 않음)"""

    export_requested = Signal(bool)  # 우클릭 "내보내기" - True 면 보관 항목 전체

    def __init__(
        self, snippets_provider, custom_tags_provider, add_custom_tag, parent=None
    ):
        """snippets_provider: () -> {트리거: 문구} (입력칸 스니펫 치환)
        custom_tags_provider: () -> [{"id", "name", "color"}] (사용자 태그, widget_config.custom_tags)
        add_custom_tag: (이름, 색) -> 새 태그 id (cfg 에 추가하고 저장)"""
        super().__init__(parent)
        self._snippets_provider = snippets_provider
        self._custom_tags_provider = custom_tags_provider
        self._add_custom_tag = add_custom_tag
        self._items = todo_store.load_todos()
        todo_tree.detach_orphans(self._items)
        self._rows = []
        self._selected = set()  # 선택한 항목 id
        self._anchor_id = (
            None  # 마지막으로 클릭한 항목 (Shift 범위 기준 / 하위 추가 대상)
        )
        # 거르는 중에 보이는 항목 id (todo_filter.visible) / None 이면 전체
        self._shown_ids = None

        # 드래그 중 상태 (_begin_drag ~ _end_drag)
        self._drag_ids = None  # 옮길 항목 id (화면 순서) / None 이면 드래그 중 아님
        self._drag_moving = set()  # 옮길 항목 + 그 하위 (놓을 수 없는 자리)
        self._drag_target = None  # _drop_target 결과
        self._drag_ghost = None  # 커서를 따라다니는 행 그림
        self._drag_hotspot = QPoint()
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(AUTO_SCROLL_MS)
        self._scroll_timer.timeout.connect(self._auto_scroll)

        # 검색 하이라이트: 검색어가 바뀌면 진하게 -> HIGHLIGHT_HOLD_MS 유지 -> 서서히 지움
        self._mark_query = ""
        self._mark_level = 0.0
        self._mark_hold = QTimer(self)
        self._mark_hold.setSingleShot(True)
        self._mark_hold.setInterval(HIGHLIGHT_HOLD_MS)
        self._mark_fade = QVariantAnimation(self)
        self._mark_fade.setStartValue(1.0)
        self._mark_fade.setEndValue(0.0)
        self._mark_fade.setDuration(HIGHLIGHT_FADE_MS)
        self._mark_fade.valueChanged.connect(self._set_mark_level)
        self._mark_hold.timeout.connect(self._mark_fade.start)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.filter_bar = FilterBar()  # 검색 / 날짜별 보기 (Ctrl+F, 우클릭 "검색")
        self.filter_bar.changed.connect(self._on_filter_changed)
        self.filter_bar.close_requested.connect(self.close_search)
        self.filter_bar.hide()
        root.addWidget(self.filter_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(20)
        # 휠 / 자동 스크롤로 목록이 움직이면 놓을 자리 표시도 다시 계산
        self.scroll.verticalScrollBar().valueChanged.connect(self._update_drag)

        self.container = QWidget()
        # 행을 클릭하면 목록이 포커스를 받아 Esc(선택 해제)를 받는다
        self.container.setFocusPolicy(Qt.ClickFocus)
        self.container.installEventFilter(self)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(2)

        self.empty_label = QLabel(EMPTY_TEXT)
        self.list_layout.addWidget(self.empty_label)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)

        self.drop_line = QFrame(self.container)  # 행 사이에 놓일 자리 표시
        self.drop_line.hide()
        self.drop_box = QFrame(self.container)  # 하위로 들어갈 행 표시
        self.drop_box.hide()
        root.addWidget(self.scroll, 1)

        self.input = TodoInput(self.reminders, snippets_provider)
        self.input.setPlaceholderText(PLACEHOLDER)
        self.input.returnPressed.connect(self._on_input_return)
        self.input.escaped.connect(self._on_input_escaped)
        root.addWidget(self.input)

        self.apply_appearance()
        self._rebuild()

    def apply_appearance(self):
        """현재 테마(theme.current())로 다시 입힌다. 글자 크기 / 색은 우패널 설정을 따른다."""
        t = theme.current()
        self.setStyleSheet(_panel_style(t))
        self.empty_label.setStyleSheet(
            f"font-size: {px(11, t.todo_scale)}px; color: {t.text_sub};"
        )
        self.drop_line.setStyleSheet(f"background: {t.accent}; border: none;")
        self.drop_box.setStyleSheet(
            f"background: transparent; border: {DROP_BOX_BORDER}px solid {t.accent};"
            f" border-radius: {ROW_RADIUS}px;"
        )
        self.refresh_rows()

    # ==================================================
    # 조회
    # ==================================================
    def items(self) -> list:
        """화면 목록 사본 (내보내기용)"""
        return list(self._items)

    def has_done(self) -> bool:
        return any(item["done"] for item in self._items)

    def reminders(self) -> list:
        """미완료 리마인더 [(datetime, 본문)]"""
        result = []
        for item in self._items:
            due = todo_store.due_at(item)
            if due is not None and not item["done"]:
                result.append((due, todo_store.strip_reminder(item["text"])))
        return result

    def _find(self, item_id: str):
        return next((item for item in self._items if item["id"] == item_id), None)

    def _tag_color(self, key):
        """태그 키의 색. 기본 태그 / 사용자 태그 순으로 찾고, 없으면 None"""
        if key in TAG_COLORS:
            return TAG_COLORS[key][1]
        return next(
            (tag["color"] for tag in self._custom_tags_provider() if tag["id"] == key),
            None,
        )

    def _selected_ids(self) -> list:
        """선택한 항목 id (화면 순서)"""
        return [
            row.item["id"] for row in self._rows if row.item["id"] in self._selected
        ]

    # ==================================================
    # 변경 (모두 저장까지 수행)
    # ==================================================
    def add_item(self, text: str):
        """선택한 항목이 있으면 그 하위 맨 뒤로 넣는다 (마지막으로 클릭한 항목 우선).
        거르는 중이면 새 항목이 숨지 않도록 전체 보기로 돌아간다 (검색 줄은 열어 둔다)."""
        self.filter_bar.reset()
        self._stop_highlight()
        item = todo_store.new_item(text)
        self._items.append(item)
        parent_id = self._add_parent_id()
        if parent_id is not None:
            # 완료된 상위 아래로 들어가면 상위는 다시 미완료가 된다 (todo_tree.move)
            todo_tree.move(self._items, item["id"], parent_id, None)
            todo_tree.expand_ancestors(self._items, item["id"])  # 접힌 상위면 펼쳐서 보이게
        self._save_and_rebuild()
        self._reveal(next(row for row in self._rows if row.item is item))

    def toggle_collapse(self, item_id: str):
        """▸/▾ 버튼: 하위를 접거나 펼친다 (숨은 하위는 _rebuild 가 선택에서 뺀다)"""
        item = self._find(item_id)
        if item is not None and todo_tree.set_collapsed(
            self._items, item_id, not item.get("collapsed")
        ):
            self._save_and_rebuild()

    def _add_parent_id(self):
        if self._anchor_id in self._selected:
            return self._anchor_id
        selected = self._selected_ids()
        return selected[0] if selected else None

    def set_done(self, item_id: str, done: bool):
        """완료하면 하위도 모두 완료, 해제하면 상위도 모두 해제"""
        if todo_tree.set_done(self._items, item_id, done):
            self._save_and_rebuild()

    def edit_item(self, item_id: str, text: str):
        item = self._find(item_id)
        if item is None:
            return
        if todo_store.parse_reminder(text) != todo_store.parse_reminder(item["text"]):
            # 리마인더 시각을 바꿨다면 미룬 시각/알림 기록을 초기화해 새로 알리도록
            item["snooze_until"] = None
            item["fired"] = None
        item["text"] = text
        self._save_and_rebuild()

    def delete_item(self, item_id: str):
        """항목만 지운다. 하위 항목은 한 단계 위로 올라간다."""
        if todo_tree.remove_promote(self._items, item_id):
            self._save_and_rebuild()

    def delete_selected(self):
        """우클릭 "삭제": 선택 항목을 완료 처리 없이 지운다. 하위는 한 단계씩 위로 올라간다."""
        changed = False
        for item_id in self._selected_ids():
            changed = todo_tree.remove_promote(self._items, item_id) or changed
        if changed:
            self._save_and_rebuild()

    def set_tag(self, tag):
        """우클릭 "태그": 선택 항목 모두에 태그(todo_store.TAGS 중 하나 / None)를 붙인다."""
        changed = False
        for item in self._items:
            if item["id"] in self._selected and item.get("tag") != tag:
                item["tag"] = tag
                changed = True
        if changed:
            self._save_and_rebuild()

    def clear_done(self):
        """완료 항목을 목록에서 뺀다. DB 에서는 지우지 않고 보관 처리한다."""
        todo_store.archive_items([item["id"] for item in self._items if item["done"]])
        self._items = [item for item in self._items if not item["done"]]
        self._save_and_rebuild()

    def snooze(self, item_id: str, until: datetime):
        item = self._find(item_id)
        if item is not None:
            item["snooze_until"] = until.strftime(todo_store.DATETIME_FMT)
            item["fired"] = None
            self._save_and_rebuild()

    def pop_due(self, now: datetime) -> list:
        """알릴 차례가 된 항목들을 알림 처리(fired)하고 돌려준다."""
        due_items = [item for item in self._items if todo_store.is_due(item, now)]
        for item in due_items:
            item["fired"] = todo_store.due_key(todo_store.due_at(item))
        if due_items:
            todo_store.save_todos(self._items)
        return due_items

    # ==================================================
    # 표시
    # ==================================================
    def refresh_rows(self):
        """지난 리마인더 색 등 시간에 따라 바뀌는 표시만 갱신.
        거르는 중에 시간이 지나 보일 항목이 바뀌면(오늘 -> 지연 등) 목록을 다시 만든다."""
        now = datetime.now().astimezone()
        if self._filtering() and self._visible(now)[0] != self._shown_ids:
            self._rebuild()
            return
        self._update_counts(now)
        for row in self._rows:
            row.render(now)

    # ==================================================
    # 검색 / 날짜별 보기
    # ==================================================
    def open_search(self):
        """Ctrl+F / 우클릭 "검색": 검색 줄을 열고 검색칸으로 커서 이동 (이미 열려 있으면 이동만)"""
        if self.filter_bar.isHidden():
            self.filter_bar.show()
            self._update_counts(datetime.now().astimezone())
        self.filter_bar.edit.setFocus(Qt.ShortcutFocusReason)
        self.filter_bar.edit.selectAll()

    def close_search(self):
        """검색 줄을 닫고 필터를 푼다 (검색칸에서 빠져 E / C 같은 글자 단축키가 다시 동작하도록)"""
        self.filter_bar.edit.clearFocus()
        self.filter_bar.reset()
        self.filter_bar.hide()
        self._stop_highlight()
        self._rebuild()

    def _on_filter_changed(self):
        """보기 / 검색어가 바뀜. 검색어가 바뀌었을 때만 하이라이트를 다시 시작한다 (칩만 바꾸면 그대로)."""
        query = self.filter_bar.query()
        if query != self._mark_query:
            if query.strip():
                self._mark_query = query
                self._mark_fade.stop()
                self._mark_level = 1.0
                self._mark_hold.start()
            else:
                self._stop_highlight()
        self._rebuild()

    def _stop_highlight(self):
        self._mark_hold.stop()
        self._mark_fade.stop()
        self._mark_query = ""
        self._mark_level = 0.0

    def _set_mark_level(self, level):
        self._mark_level = level
        for row in self._rows:
            row.mark_level = level
            row.render()

    def _filtering(self) -> bool:
        bar = self.filter_bar
        return not bar.isHidden() and todo_filter.is_active(bar.view(), bar.query())

    def _visible(self, now: datetime):
        return todo_filter.visible(
            self._items, self.filter_bar.view(), self.filter_bar.query(), now
        )

    def _update_counts(self, now: datetime):
        if not self.filter_bar.isHidden():
            self.filter_bar.set_counts(
                todo_filter.counts(self._items, self.filter_bar.query(), now)
            )

    def _reveal(self, row: "TodoRow"):
        """row 가 보이도록 스크롤한다. 목록을 막 다시 만들었으면 스크롤 범위가 아직 옛 크기라서
        (레이아웃 요청이 대기 중) 레이아웃을 지금 끝낸 뒤에 맞춘다 - 맨 아래 행이 범위 밖으로 잘리지 않게"""
        self.list_layout.activate()
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        self.scroll.ensureWidgetVisible(row)

    def _save_and_rebuild(self):
        todo_tree.detach_orphans(
            self._items
        )  # 상위가 지워지거나 보관된 항목은 최상위로
        todo_store.save_todos(self._items)
        self._rebuild()

    @staticmethod
    def _sort_key(item: dict):
        due = todo_store.due_at(item)  # 행에 표시되는 시각(미룬 시각 우선)과 같은 기준
        return (item["done"], due is None, due or datetime.min.replace(tzinfo=UTC))

    def _rebuild(self):
        """목록을 지금 상태로 맞춘다. 있던 항목의 행은 다시 쓰고(상태만 갱신) 새 항목만 행을 만든다.
        체크 / 접기마다 행을 모두 새로 만들면 항목이 많을 때 눈에 띄게 느려진다."""
        self._end_drag()  # 드래그 중이던 행이 사라질 수 있으므로 (리마인더 팝업에서 완료 등)

        # 하위는 상위 바로 밑에. 형제끼리 미완료 -> 완료 순, 각각 리마인더 일시가 빠른 순
        # 리마인더 없는 항목은 그 뒤에 self._items 순서(= 드래그로 정한 순서) 그대로 (안정 정렬)
        # 거르는 중에는 접힘을 무시한다 (맞는 항목이 접힌 상위 아래에 숨지 않게)
        ordered = todo_tree.flatten(
            self._items, self._sort_key, hide_collapsed=not self._filtering()
        )
        parents = {item.get("parent_id") for item in self._items}
        now = datetime.now().astimezone()
        context = set()
        self._shown_ids = None
        if self._filtering():
            # 거를 때도 상위가 함께 남으므로 펼친 순서 / 레벨은 그대로 둔다
            self._shown_ids, context = self._visible(now)
            ordered = [pair for pair in ordered if pair[0]["id"] in self._shown_ids]
        self._update_counts(now)

        old = {row.item["id"]: row for row in self._rows}
        self._rows = []
        for item, depth in ordered:
            row = old.pop(item["id"], None) or self._new_row()
            row.mark_query = self._mark_query
            row.mark_level = self._mark_level
            row.set_state(
                item,
                depth,
                context=item["id"] in context,
                has_children=item["id"] in parents,
            )
            self._rows.append(row)
        for row in old.values():  # 지워지거나 보관되거나 숨은 항목
            self._drop_row(row)
        # 화면 순서대로 놓는다 (자리가 바뀐 행만 옮김)
        for idx, row in enumerate(self._rows):
            placed = self.list_layout.itemAt(idx)
            if placed is None or placed.widget() is not row:
                self.list_layout.removeWidget(row)
                self.list_layout.insertWidget(idx, row)
            if row.isHidden():
                # 새 행은 지금 보여야 첫 레이아웃 계산에 들어간다. 레이아웃의 지연 표시를 기다리면
                # 그 사이 목록 높이가 잠깐 줄어 스크롤 범위가 0 이 되고 위치가 맨 위로 잘린다
                row.show()

        self.empty_label.setText(
            EMPTY_FILTERED_TEXT if self._shown_ids is not None else EMPTY_TEXT
        )
        self.empty_label.setVisible(not ordered)
        # 지워지거나 보관된 항목, 거르는 중에 숨은 항목은 선택에서 뺀다 (숨은 항목에 태그 등이 붙지 않게)
        ids = {row.item["id"] for row in self._rows}
        self._selected &= ids
        if self._anchor_id not in ids:
            self._anchor_id = None
        self._apply_selection()

    def _new_row(self) -> "TodoRow":
        row = TodoRow(
            self.reminders,
            self._snippets_provider,
            self._tag_color,
            parent=self.container,
        )
        row.toggled.connect(self.set_done)
        row.deleted.connect(self.delete_item)
        row.edited.connect(self.edit_item)
        row.collapse_toggled.connect(self.toggle_collapse)
        row.clicked.connect(self._on_row_clicked)
        row.drag_started.connect(self._begin_drag)
        row.drag_moved.connect(self._update_drag)
        row.drag_released.connect(self._finish_drag)
        row.drag_canceled.connect(self._end_drag)
        return row

    def _drop_row(self, row: "TodoRow"):
        focus = QApplication.focusWidget()
        if focus is not None and row.isAncestorOf(focus):
            # 포커스를 가진 행을 숨기면 Qt 가 다음 위젯으로 포커스를 넘기며 목록을 스크롤한다
            self.container.setFocus(Qt.OtherFocusReason)
        row.hide()
        self.list_layout.removeWidget(row)
        row.deleteLater()

    # ==================================================
    # 선택
    # ==================================================
    def _on_row_clicked(self, row: "TodoRow", modifiers):
        """클릭: 그 행만 / Ctrl: 하나씩 추가·빼기 / Shift: 마지막으로 클릭한 행부터 범위"""
        item_id = row.item["id"]
        order = [r.item["id"] for r in self._rows]
        if modifiers & Qt.ShiftModifier and self._anchor_id in order:
            a, b = sorted((order.index(self._anchor_id), order.index(item_id)))
            span = set(order[a : b + 1])
            self._selected = (
                self._selected | span if modifiers & Qt.ControlModifier else span
            )
        elif modifiers & Qt.ControlModifier:
            if item_id in self._selected:
                self._selected.discard(item_id)
            else:
                self._selected.add(item_id)
                self._anchor_id = item_id
        else:
            self._selected = {item_id}
            self._anchor_id = item_id
        self.container.setFocus(Qt.MouseFocusReason)
        self._apply_selection()

    def _select_only(self, item_id):
        self._selected = {item_id}
        self._anchor_id = item_id
        self._apply_selection()

    def clear_selection(self):
        if self._selected:
            self._selected.clear()
            self._anchor_id = None
            self._apply_selection()

    def _apply_selection(self):
        self.container.update()  # 선택 테두리 (_paint_selection)
        # 선택한 채로 입력하면 하위로 들어간다는 것을 입력칸에 보여준다
        self.input.setPlaceholderText(
            PLACEHOLDER_CHILD if self._selected else PLACEHOLDER
        )

    def _selection_blocks(self) -> list:
        """화면에서 이어진 선택 행 묶음 [[row, ...], ...]"""
        blocks, block = [], []
        for row in self._rows:
            if row.item["id"] in self._selected:
                block.append(row)
            elif block:
                blocks.append(block)
                block = []
        if block:
            blocks.append(block)
        return blocks

    def _paint_selection(self):
        """선택 테두리: 이어진 선택 행 묶음마다 둥근 사각형 하나.
        왼쪽 끝은 묶음에서 가장 얕은 레벨의 들여쓰기에 맞춘다. (container 의 Paint 이벤트에서 부름)"""
        blocks = self._selection_blocks()
        if not blocks:
            return
        painter = QPainter(self.container)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(theme.current().accent), SELECTED_BORDER))
        half = SELECTED_BORDER / 2
        for block in blocks:
            top = block[0].geometry().top()
            bottom = block[-1].geometry().bottom() + 1
            left = min(row.geometry().left() + row.indent() for row in block)
            right = block[0].geometry().right() + 1
            rect = QRectF(left, top, right - left, bottom - top)
            painter.drawRoundedRect(
                rect.adjusted(half, half, -half, -half), ROW_RADIUS, ROW_RADIUS
            )

    # ==================================================
    # 우클릭 메뉴
    # ==================================================
    def _row_at(self, global_pos: QPoint):
        for row in self._rows:
            if row.rect().contains(row.mapFromGlobal(global_pos)):
                return row
        return None

    def contextMenuEvent(self, event):
        """우패널 메뉴. 선택하지 않은 행에서 열면 그 행만 선택하고, 빈 곳에서 열면 선택을 푼다."""
        row = self._row_at(event.globalPos())
        if row is None:
            self.clear_selection()
        elif row.item["id"] not in self._selected:
            self._select_only(row.item["id"])
        t = theme.current()
        menu = QMenu(self)
        menu.setStyleSheet(theme.menu_style(t))

        menu.addAction("검색", self.open_search)
        menu.addSeparator()
        act_clear = menu.addAction("완료 항목 정리", self.clear_done)
        act_clear.setEnabled(self.has_done())
        export_menu = menu.addMenu("내보내기")
        export_menu.setStyleSheet(menu.styleSheet())
        act_active = export_menu.addAction(
            "화면 목록…", lambda: self.export_requested.emit(False)
        )
        act_active.setEnabled(bool(self._items))
        act_archived = export_menu.addAction(
            "보관 항목 전체…", lambda: self.export_requested.emit(True)
        )
        act_archived.setEnabled(bool(todo_store.load_archived()))
        menu.addSeparator()

        menu.addAction("추가", self.focus_input)
        act_delete = menu.addAction("삭제", self.delete_selected)
        act_delete.setEnabled(bool(self._selected))

        # 선택 항목들의 지금 태그는 메뉴 한 칸을 강조색 테두리로 감싼다 (checked 항목).
        # 다른 칸도 같은 두께의 투명 테두리를 둬서 글자 위치가 어긋나지 않게 하고, 체크 표시는 숨긴다
        tag_menu = menu.addMenu("태그")
        tag_menu.setStyleSheet(
            menu.styleSheet()
            + f"""
            QMenu::item {{
                border: {TAG_CHECKED_BORDER}px solid transparent;
                border-radius: {ROW_RADIUS}px;
            }}
            QMenu::item:checked {{ border: {TAG_CHECKED_BORDER}px solid {t.accent}; }}
            QMenu::indicator {{ width: 0px; height: 0px; }}
            """
        )
        tag_menu.setEnabled(bool(self._selected))
        tags = {item.get("tag") for item in self._items if item["id"] in self._selected}
        # 선택 항목이 모두 같은 태그일 때만 표시 ("태그 없음"은 표시하지 않음)
        current = tags.pop() if len(tags) == 1 else None

        def add_tag_action(icon, name, key):
            action = tag_menu.addAction(icon, name, lambda _=False: self.set_tag(key))
            if key is not None and key == current:
                action.setCheckable(True)
                action.setChecked(True)

        for key in todo_store.TAGS:
            name, color = TAG_COLORS[key]
            add_tag_action(_tag_icon(color), name, key)
        tag_menu.addSeparator()
        add_tag_action(_tag_icon("", t.menu_disabled), "태그 없음", None)
        # 태그 없음 아래: 사용자가 추가한 태그 + 추가
        for tag in self._custom_tags_provider():
            add_tag_action(_tag_icon(tag["color"]), tag["name"], tag["id"])
        tag_menu.addAction("+ 태그 추가…", self._create_tag)

        menu.exec(event.globalPos())

    def _create_tag(self):
        """태그 메뉴 "+ 태그 추가…": 이름 / 색을 골라 사용자 태그로 저장하고 선택 항목에 붙인다."""
        dialog = TagDialog(parent=self)
        if dialog.exec_over(self.window()):
            self.set_tag(self._add_custom_tag(dialog.name(), dialog.color()))

    # ==================================================
    # 드래그로 순서 / 레벨 변경
    # ==================================================
    def _begin_drag(self, row: "TodoRow"):
        """선택한 행을 끌면 선택 항목 전부, 아니면 그 행만 (선택도 그 행으로 바뀐다)"""
        item_id = row.item["id"]
        if item_id not in self._selected:
            self._select_only(item_id)
        if self._shown_ids is not None:
            return  # 거르는 중에는 옮기지 않는다 - 숨은 형제 사이 어디에 놓일지 알 수 없다
        self._drag_ids = todo_tree.top_selected(self._items, self._selected_ids())
        self._drag_moving = set(self._drag_ids)
        for moving_id in self._drag_ids:
            self._drag_moving.update(
                other["id"] for other in todo_tree.descendants(self._items, moving_id)
            )
        self._drag_target = None

        self._drag_hotspot = row.mapFromGlobal(QCursor.pos())
        self._drag_ghost = self._make_ghost(row, len(self._drag_ids))
        self._drag_ghost.move(QCursor.pos() - self._drag_hotspot)
        self._drag_ghost.show()
        self._scroll_timer.start()
        self._update_drag()

    def _make_ghost(self, row: "TodoRow", count: int) -> QLabel:
        """커서를 따라다니는 반투명 행 그림 (여러 개면 개수 배지)"""
        t = theme.current()
        shot = row.grab()
        ratio = shot.devicePixelRatio()
        pixmap = QPixmap(shot.size())
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, row.width() - 1, row.height() - 1)
        painter.setPen(QPen(QColor(t.accent), 1))
        painter.setBrush(QColor(t.bg))
        painter.drawRoundedRect(rect, ROW_RADIUS, ROW_RADIUS)
        painter.drawPixmap(0, 0, shot)
        if count > 1:
            badge = QRectF(row.width() - 26, 2, 22, 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t.accent))
            painter.drawRoundedRect(badge, 8, 8)
            painter.setPen(QColor(t.on_accent))
            painter.drawText(badge, Qt.AlignCenter, str(count))
        painter.end()

        ghost = QLabel(
            None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
        )
        ghost.setAttribute(Qt.WA_TranslucentBackground, True)
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ghost.setAttribute(Qt.WA_ShowWithoutActivating, True)
        ghost.setWindowOpacity(DRAG_GHOST_OPACITY)
        ghost.setPixmap(pixmap)
        ghost.resize(row.size())
        return ghost

    def _cursor_in_list(self) -> bool:
        viewport = self.scroll.viewport()
        return viewport.rect().contains(viewport.mapFromGlobal(QCursor.pos()))

    def _update_drag(self, *_):
        """커서 위치(또는 스크롤)에 맞춰 끌고 가는 그림과 놓을 자리 표시를 옮긴다."""
        if self._drag_ids is None:
            return
        pos = QCursor.pos()
        self._drag_ghost.move(pos - self._drag_hotspot)
        target = None
        if self._cursor_in_list():
            target = self._drop_target(self.container.mapFromGlobal(pos).y())
        self._drag_target = target
        self._show_drop_mark(target[2] if target is not None else None)

    def _finish_drag(self):
        ids, target = self._drag_ids, self._drag_target
        self._end_drag()
        if ids and target is not None:
            # 놓은 행이 이 시그널을 보내는 중이므로 행을 지우는(rebuild) 이동은 끝난 뒤에
            QTimer.singleShot(0, lambda: self._move_items(ids, target[0], target[1]))

    def _end_drag(self):
        """드래그 끝 / 취소(Esc)"""
        if self._drag_ids is None:
            return
        self._drag_ids = None
        self._drag_moving = set()
        self._drag_target = None
        self._scroll_timer.stop()
        self._drag_ghost.hide()
        self._drag_ghost.deleteLater()
        self._drag_ghost = None
        self._show_drop_mark(None)

    def _drop_target(self, y: int):
        """끌고 있는 항목들을 y 에 놓았을 때의 자리. 행 높이를 3등분해서
        위쪽(행 사이 여백 포함)은 그 행 앞, 가운데는 그 행의 하위 맨 뒤, 아래쪽은 다음 행 앞.

        Returns
        -------
        None : 끌고 있는 항목(또는 그 하위) 위 - 놓아도 아무 일 없음
        (새 상위 id, 이 id 앞으로 / None 이면 형제 맨 뒤, 표시) :
            표시는 ("line", 표시선 y, 레벨) 또는 ("box", 하위로 들어갈 행)
        """
        moving = self._drag_moving
        for row in self._rows:
            geo = row.geometry()
            if row.item["id"] in moving and geo.top() <= y <= geo.bottom():
                return None
        rows = [row for row in self._rows if row.item["id"] not in moving]
        if not rows:
            return None

        for idx, row in enumerate(rows):
            geo = row.geometry()
            if y > geo.bottom():
                continue
            third = geo.height() / 3
            if y < geo.top() + third:
                return (
                    row.item["parent_id"],
                    row.item["id"],
                    ("line", geo.top() - 1, row.depth),
                )
            if y < geo.bottom() - third:
                return row.item["id"], None, ("box", row)
            if idx + 1 < len(rows):
                nxt = rows[idx + 1]
                return (
                    nxt.item["parent_id"],
                    nxt.item["id"],
                    ("line", geo.bottom() + 1, nxt.depth),
                )
            break
        return None, None, ("line", rows[-1].geometry().bottom() + 1, 0)

    def _show_drop_mark(self, mark):
        """_drop_target 의 표시를 그린다. None 이면 모두 숨긴다."""
        if mark is not None and mark[0] == "line":
            _, y, depth = mark
            x = _indent(depth)
            self.drop_line.setGeometry(
                x,
                y - DROP_LINE_WIDTH // 2,
                self.container.width() - 4 - x,
                DROP_LINE_WIDTH,
            )
            self.drop_line.raise_()
            self.drop_line.show()
        else:
            self.drop_line.hide()

        if mark is not None and mark[0] == "box":
            row = mark[1]
            self.drop_box.setGeometry(row.geometry().adjusted(row.indent(), 0, 0, 0))
            self.drop_box.raise_()
            self.drop_box.show()
        else:
            self.drop_box.hide()

    def _auto_scroll(self):
        """드래그 중 커서가 목록 위/아래 끝(또는 그 바깥)에 있으면 계속 스크롤한다.
        끝에서 멀어질수록 빠르게. 스크롤되면 valueChanged 로 놓을 자리가 다시 계산된다."""
        viewport = self.scroll.viewport()
        pos = viewport.mapFromGlobal(QCursor.pos())
        if not (
            -AUTO_SCROLL_MARGIN <= pos.x() <= viewport.width() + AUTO_SCROLL_MARGIN
        ):
            return
        if pos.y() < AUTO_SCROLL_MARGIN:
            depth = AUTO_SCROLL_MARGIN - pos.y()
        elif pos.y() > viewport.height() - AUTO_SCROLL_MARGIN:
            depth = -(pos.y() - (viewport.height() - AUTO_SCROLL_MARGIN))
        else:
            return
        step = min(AUTO_SCROLL_MAX_STEP, 2 + abs(depth) // 3)
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.value() - step if depth > 0 else bar.value() + step)

    def _move_items(self, ids: list, parent_id, before_id):
        """ids 를 (하위와 함께) parent_id 아래 before_id 앞으로 (None 이면 형제 맨 뒤로) 옮긴다."""
        if todo_tree.move_many(self._items, ids, parent_id, before_id):
            for item_id in ids:
                todo_tree.expand_ancestors(self._items, item_id)  # 접힌 상위로 넣었으면 펼침
            self._save_and_rebuild()

    # ==================================================
    # 이벤트 / 입력칸
    # ==================================================
    def eventFilter(self, obj, event):
        if obj is self.container:
            if event.type() == QEvent.Paint:
                self._paint_selection()  # 행(자식)보다 먼저, 목록 위에 그린다
            elif event.type() == QEvent.LayoutRequest:
                self.container.update()  # 행 높이가 바뀌면(수정 중 등) 테두리도 다시
            elif (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
            ):
                # 목록 빈 곳 클릭: 선택 해제 (누름은 그대로 올려 보내 위젯 창 이동은 유지)
                # 행에서 올라온 우클릭 누름까지 지우면 여러 개를 선택한 채 우클릭할 수 없다
                self.clear_selection()
            elif event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.clear_selection()
                return True
        return super().eventFilter(obj, event)

    def focus_input(self):
        """할 일 추가 단축키 / 우클릭 "추가": 입력칸으로 커서 이동 (선택은 유지 - 하위로 추가)"""
        self.input.setFocus(Qt.ShortcutFocusReason)
        self.input.end(False)

    def _on_input_escaped(self):
        """Esc: 입력을 지우고 선택을 푼 뒤 입력칸에서 빠진다 (E / C 같은 글자 단축키가 다시 동작하도록)"""
        self.input.clear()
        self.input.clearFocus()
        self.clear_selection()

    def _on_input_return(self):
        text = self.input.text().strip()
        if text:
            self.add_item(text)
        self.input.clear()

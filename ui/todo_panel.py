"""위젯 안의 TODO 리스트

  - 목록 아래 입력창에서 Enter 로 바로 추가 (별도 창 없음)
  - 입력 중 `(@` 를 치면 리마인더 피커가 떠서 `(@YYYY-MM-DD HH:mm)` 토큰을 넣는다
  - 체크하면 취소선 + 목록 아래로, 우클릭 메뉴 "완료 항목 정리" 로 일괄 보관(DB 에는 남음)
  - 더블클릭으로 그 자리에서 수정 (Enter/포커스 이동: 저장, Esc: 취소)
  - 리마인더 항목은 항상 위에 시각순 고정, 나머지는 드래그 앤 드롭으로 순서 변경
"""

from datetime import datetime

from PySide6.QtCore import QEvent, QMimeData, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from manager import todo_store
from ui.reminder_picker import ReminderPicker
from ui.theme import ACCENT, FONT_FAMILY, TEXT_MAIN, TEXT_SUB, TEXT_WARN


TRIGGER = "(@"
ROW_HOVER_COLOR = QColor(255, 255, 255, 24)  # 마우스를 올린 행 배경
ROW_RADIUS = 4
TODO_MIME = "application/x-taskpin-todo-id"  # 드래그 앤 드롭으로 옮기는 항목 id
AUTO_SCROLL_MARGIN = 16  # 드래그 중 목록 위/아래 끝에서 자동 스크롤되는 영역(px)
AUTO_SCROLL_STEP = 8

PANEL_STYLE = f"""
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255,255,255,50);
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QLineEdit {{
        background: rgba(255,255,255,18);
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        font-size: 12px;
        border: 1px solid rgba(255,255,255,30);
        border-radius: 6px;
        padding: 3px 6px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus {{ border: 1px solid rgba(255,255,255,90); }}
    QCheckBox {{ background: transparent; spacing: 0px; }}
    QCheckBox::indicator {{
        width: 12px;
        height: 12px;
        border: 1px solid rgba(255,255,255,130);
        border-radius: 3px;
        background: transparent;
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {TEXT_MAIN}; }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
    }}
    QPushButton#delete {{
        background: transparent;
        color: {TEXT_SUB};
        border: none;
        padding: 0px;
        font-size: 11px;
    }}
    QPushButton#delete:hover {{ color: {TEXT_WARN}; }}
"""


class TodoInput(QLineEdit):
    """`(@` 를 감지해 리마인더 피커를 띄우는 입력창"""

    escaped = Signal()
    focus_lost = Signal()

    def __init__(self, reminders_provider, parent=None):
        """reminders_provider: () -> [(datetime, 본문)]  (피커에 보여줄 기존 리마인더)"""
        super().__init__(parent)
        self._reminders_provider = reminders_provider
        self._picker = None
        self._trigger_pos = 0
        self.textEdited.connect(self._on_text_edited)

    @property
    def picker_open(self) -> bool:
        return self._picker is not None

    def _on_text_edited(self, text: str):
        pos = self.cursorPosition()
        if pos >= len(TRIGGER) and text[pos - len(TRIGGER) : pos] == TRIGGER:
            self.open_picker(pos)

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
        self.setCursorPosition(len(left) + len(token))

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


class TodoRow(QWidget):
    toggled = Signal(str, bool)
    deleted = Signal(str)
    edited = Signal(str, str)
    drag_requested = Signal(object)  # TodoRow

    def __init__(self, item: dict, reminders_provider, draggable: bool, parent=None):
        super().__init__(parent)
        self.item = item
        self.draggable = draggable
        self._editing = False
        self._hover = False
        self._press_pos = None  # 드래그 시작 판정용 누른 지점

        layout = QHBoxLayout(self)
        # 좌우 여백은 hover 배경이 체크박스/삭제 버튼에 붙지 않게
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.check = QCheckBox()
        self.check.setCursor(Qt.PointingHandCursor)
        self.check.setChecked(item["done"])
        self.check.toggled.connect(lambda on: self.toggled.emit(self.item["id"], on))

        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        # RichText 라벨은 기본값(링크 클릭)이면 마우스 이동을 삼켜서 행의 드래그가 시작되지 않는다
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label.setToolTip(
            "더블클릭하여 수정 · 드래그하여 순서 변경" if draggable else "더블클릭하여 수정"
        )
        self.label.installEventFilter(self)

        self.editor = TodoInput(reminders_provider)
        self.editor.hide()
        self.editor.returnPressed.connect(self._commit_edit)
        self.editor.focus_lost.connect(self._commit_edit)
        self.editor.escaped.connect(self._cancel_edit)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setObjectName("delete")
        self.btn_delete.setFixedSize(16, 16)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setToolTip("삭제")
        self.btn_delete.clicked.connect(lambda: self.deleted.emit(self.item["id"]))
        # hover 할 때만 보이되, 숨겨도 자리는 유지해서 줄바꿈이 흔들리지 않게
        policy = self.btn_delete.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.btn_delete.setSizePolicy(policy)
        self.btn_delete.hide()

        layout.addWidget(self.check, 0, Qt.AlignTop)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.btn_delete, 0, Qt.AlignTop)

        self.render()

    def render(self, now: datetime = None):
        now = now or datetime.now()
        done = self.item["done"]
        body = todo_store.to_html(self.item["text"]) or "&nbsp;"
        color = TEXT_SUB if done else TEXT_MAIN
        html = f'<span style="color:{color};">{body}</span>'
        if done:
            html = f"<s>{html}</s>"

        due = todo_store.due_at(self.item)
        if due is not None:
            chip_color = TEXT_WARN if (not done and due <= now) else TEXT_SUB
            html += (
                f'&nbsp;<span style="color:{chip_color}; font-size:11px;">'
                f"⏰&nbsp;{due:%m/%d %H:%M}</span>"
            )
        self.label.setText(
            f'<div style="font-family:{FONT_FAMILY}; font-size:12px;">{html}</div>'
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
        self.editor.hide()
        self.label.show()

    # ---- 이벤트 ----
    def eventFilter(self, obj, event):
        if obj is self.label and event.type() == QEvent.MouseButtonDblClick:
            self.start_edit()
            return True
        return super().eventFilter(obj, event)

    # 드래그 가능한 행은 누름을 받아서 위젯 창 이동으로 넘어가지 않게 한다
    def mousePressEvent(self, event):
        if self.draggable and not self._editing and event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= QApplication.startDragDistance():
                self._press_pos = None
                self.drag_requested.emit(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

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
        if not self._hover:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), ROW_RADIUS, ROW_RADIUS)
        painter.fillPath(path, ROW_HOVER_COLOR)


class TodoPanel(QWidget):
    """TODO 목록 + 입력창. 상태는 todo_store 로 바로바로 저장한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = todo_store.load_todos()
        self._rows = []
        self._pending_move = None  # 드롭된 (옮길 id, 이 id 앞으로 / None 이면 그룹 맨 뒤로)
        self.setStyleSheet(PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(20)

        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(2)

        self.empty_label = QLabel("할 일이 없습니다")
        self.empty_label.setStyleSheet(f"font-size: 11px; color: {TEXT_SUB};")
        self.list_layout.addWidget(self.empty_label)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)

        # ---- 드래그 앤 드롭 (행들은 드롭을 받지 않으므로 container 로 올라온다) ----
        self.container.setAcceptDrops(True)
        self.container.installEventFilter(self)
        self.drop_line = QFrame(self.container)  # 놓일 자리 표시
        self.drop_line.setStyleSheet(f"background: {ACCENT}; border: none;")
        self.drop_line.hide()
        root.addWidget(self.scroll, 1)

        self.input = TodoInput(self.reminders)
        self.input.setPlaceholderText("+ 할 일 추가 · (@ 리마인더")
        self.input.returnPressed.connect(self._on_input_return)
        self.input.escaped.connect(self.input.clear)
        root.addWidget(self.input)

        self._rebuild()

    # ==================================================
    # 조회
    # ==================================================
    def items(self) -> list:
        return self._items

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

    # ==================================================
    # 변경 (모두 저장까지 수행)
    # ==================================================
    def add_item(self, text: str):
        item = todo_store.new_item(text)
        self._items.append(item)
        self._save_and_rebuild()
        # 레이아웃이 갱신된 뒤에 새 항목이 보이도록 스크롤
        row = next(row for row in self._rows if row.item is item)
        QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(row))

    def set_done(self, item_id: str, done: bool):
        item = self._find(item_id)
        if item is not None and item["done"] != done:
            item["done"] = done
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
        self._items = [item for item in self._items if item["id"] != item_id]
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
        """지난 리마인더 색 등 시간에 따라 바뀌는 표시만 갱신"""
        now = datetime.now()
        for row in self._rows:
            row.render(now)

    def _save_and_rebuild(self):
        todo_store.save_todos(self._items)
        self._rebuild()

    @staticmethod
    def _sort_key(item: dict):
        due = todo_store.due_at(item)  # 행에 표시되는 시각(미룬 시각 우선)과 같은 기준
        return (item["done"], due is None, due or datetime.min)

    @staticmethod
    def _is_draggable(item: dict) -> bool:
        """리마인더 항목은 시각순으로 고정, 나머지만 사용자가 순서를 정한다."""
        return todo_store.due_at(item) is None

    def _rebuild(self):
        for row in self._rows:
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []

        # 미완료 -> 완료 순, 각각 리마인더 일시가 빠른 순
        # 리마인더 없는 항목은 그 뒤에 self._items 순서(= 드래그로 정한 순서) 그대로 (안정 정렬)
        ordered = sorted(self._items, key=self._sort_key)
        for idx, item in enumerate(ordered):
            row = TodoRow(item, self.reminders, self._is_draggable(item))
            row.toggled.connect(self.set_done)
            row.deleted.connect(self.delete_item)
            row.edited.connect(self.edit_item)
            row.drag_requested.connect(self._start_drag)
            self.list_layout.insertWidget(idx, row)
            self._rows.append(row)

        self.empty_label.setVisible(not ordered)

    # ==================================================
    # 드래그 앤 드롭으로 순서 변경
    # ==================================================
    def _start_drag(self, row: "TodoRow"):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(TODO_MIME, row.item["id"].encode())
        drag.setMimeData(mime)
        drag.setPixmap(row.grab())
        drag.setHotSpot(row.mapFromGlobal(QCursor.pos()))

        self._pending_move = None
        drag.exec(Qt.MoveAction)
        self.drop_line.hide()

        # 드래그 루프 안에서 행을 지우면(rebuild) 드래그를 시작한 행이 사라지므로 끝난 뒤에 옮긴다
        if self._pending_move is not None:
            self._move_item(*self._pending_move)
            self._pending_move = None

    def _drop_target(self, item: dict, y: int):
        """같은 그룹(완료 여부가 같은 드래그 가능 항목) 행 사이에서 y 에 해당하는 자리

        Returns
        -------
        (이 행 앞에 놓음 / None 이면 그룹 맨 뒤, 표시선 y)
        """
        group = [
            row for row in self._rows
            if self._is_draggable(row.item) and row.item["done"] == item["done"]
        ]
        for row in group:
            geo = row.geometry()
            if y < geo.center().y():
                return row, geo.top() - 1
        return None, group[-1].geometry().bottom() + 1

    def _dragged_item(self, event):
        if not event.mimeData().hasFormat(TODO_MIME):
            return None
        item_id = bytes(event.mimeData().data(TODO_MIME)).decode()
        return self._find(item_id)

    def eventFilter(self, obj, event):
        if obj is self.container and event.type() in (
            QEvent.DragEnter, QEvent.DragMove, QEvent.Drop,
        ):
            item = self._dragged_item(event)
            if item is None:
                event.ignore()
                return True

            y = event.position().toPoint().y()
            target, line_y = self._drop_target(item, y)
            if event.type() == QEvent.Drop:
                self.drop_line.hide()
                self._pending_move = (item["id"], target.item["id"] if target else None)
            else:
                self.drop_line.setGeometry(0, line_y - 1, self.container.width() - 4, 2)
                self.drop_line.raise_()
                self.drop_line.show()
                self._auto_scroll(y)
            event.acceptProposedAction()
            return True

        if obj is self.container and event.type() == QEvent.DragLeave:
            self.drop_line.hide()
        return super().eventFilter(obj, event)

    def _auto_scroll(self, container_y: int):
        """목록 위/아래 끝으로 끌고 가면 스크롤"""
        viewport = self.scroll.viewport()
        y = self.container.mapTo(viewport, self.container.rect().topLeft()).y() + container_y
        bar = self.scroll.verticalScrollBar()
        if y < AUTO_SCROLL_MARGIN:
            bar.setValue(bar.value() - AUTO_SCROLL_STEP)
        elif y > viewport.height() - AUTO_SCROLL_MARGIN:
            bar.setValue(bar.value() + AUTO_SCROLL_STEP)

    def _move_item(self, item_id: str, before_id):
        """item_id 를 before_id 앞으로 (None 이면 같은 그룹의 맨 뒤로) 옮긴다."""
        item = self._find(item_id)
        if item is None or item_id == before_id:
            return
        others = [
            other for other in self._items
            if other is not item
            and self._is_draggable(other)
            and other["done"] == item["done"]
        ]
        if not others:
            return

        self._items.remove(item)
        if before_id is not None:
            idx = self._items.index(self._find(before_id))
        else:
            idx = self._items.index(others[-1]) + 1
        self._items.insert(idx, item)
        self._save_and_rebuild()

    def _on_input_return(self):
        text = self.input.text().strip()
        if text:
            self.add_item(text)
        self.input.clear()

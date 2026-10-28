"""TODO 페이지 표시 (우패널 위 / 아래 / 왼쪽 / 오른쪽 - 설정창 Appearance "페이지 표시 위치")

엑셀 시트처럼 페이지마다 독립된 할 일 목록을 둔다 (manager/todo_pages, TodoPanel).
이 줄은 보여주고 요청만 시그널로 올린다 ("멍청한 뷰").
  - 위 / 아래: [지금 페이지 이름] ... [점들][+]   이름을 더블클릭하면 이름 바꾸기
  - 왼쪽 / 오른쪽: 세로로 [점들][+]   (이름은 점의 툴팁)
  - 점: 지금 페이지는 강조색 알약, 나머지는 작은 점. 누르면 그 페이지로 (바뀔 때 알약이 옮겨 가며 늘었다 줄어든다)
  - 휠: 앞 / 뒤 페이지, 우클릭: 새 페이지 / 이름 바꾸기 / 앞·뒤로 옮기기 / 페이지 삭제
"""

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QWidget,
)

from ui import theme
from ui.theme import px

DOT = 6  # 점 지름(px)
PILL = 18  # 지금 페이지 알약 길이(px)
DOT_GAP = 6
DOT_MARGIN = 4  # 점 둘레 여백 (누르기 쉽게)
DOT_ALPHA = 80  # 다른 페이지 점 (테마의 덧칠 색)
DOT_HOVER_ALPHA = 170
PILL_ANIM_MS = 160
ADD_BUTTON_SIZE = 16


class PageDots(QWidget):
    """페이지 점. 지금 페이지는 강조색 알약, 나머지는 작은 점. 누르면 page_clicked"""

    page_clicked = Signal(int)  # 페이지 id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._current = None  # 지금 페이지 index
        self._previous = None  # 알약이 줄어드는 이전 페이지 index (애니메이션 중)
        self._progress = 1.0  # 알약 옮겨 가기 0 ~ 1
        self._hover = None
        self._vertical = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(PILL_ANIM_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_progress)

    def set_vertical(self, vertical: bool):
        self._vertical = vertical
        self.updateGeometry()
        self.update()

    def set_pages(self, pages: list, current_id: int):
        ids = [page["id"] for page in pages]
        current = ids.index(current_id) if current_id in ids else None
        # 페이지를 넘길 때만 알약을 옮겨 간다 (추가 / 삭제로 순서가 바뀌면 바로)
        moving = (
            self._current is not None
            and current != self._current
            and len(pages) == len(self._pages)
        )
        self._previous = self._current if moving else None
        self._pages = list(pages)
        self._current = current
        self._anim.stop()
        if moving:
            self._progress = 0.0
            self._anim.start()
        else:
            self._progress = 1.0
        self.updateGeometry()
        self.update()

    def _set_progress(self, value):
        self._progress = value
        self.update()

    def _length(self, idx: int) -> float:
        grow = (PILL - DOT) * self._progress
        if idx == self._current:
            return DOT + grow
        if idx == self._previous:
            return PILL - grow
        return DOT

    def _rects(self) -> list:
        rects, pos = [], DOT_MARGIN
        cross = (self.width() if self._vertical else self.height()) / 2 - DOT / 2
        for idx in range(len(self._pages)):
            length = self._length(idx)
            if self._vertical:
                rects.append(QRectF(cross, pos, DOT, length))
            else:
                rects.append(QRectF(pos, cross, length, DOT))
            pos += length + DOT_GAP
        return rects

    def sizeHint(self) -> QSize:
        count = len(self._pages)
        main = DOT_MARGIN * 2 + (count - 1) * (DOT + DOT_GAP) + PILL if count else 0
        cross = DOT + DOT_MARGIN * 2
        return QSize(cross, main) if self._vertical else QSize(main, cross)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _index_at(self, pos):
        # 점 사이 간격 절반과 둘레 여백까지 그 점으로 본다
        pad_main, pad_cross = DOT_GAP / 2, DOT_MARGIN
        dx, dy = (pad_cross, pad_main) if self._vertical else (pad_main, pad_cross)
        for idx, rect in enumerate(self._rects()):
            if rect.adjusted(-dx, -dy, dx, dy).contains(pos):
                return idx
        return None

    def paintEvent(self, event):
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for idx, rect in enumerate(self._rects()):
            if idx == self._current:
                color = QColor(t.accent)
            else:
                alpha = DOT_HOVER_ALPHA if idx == self._hover else DOT_ALPHA
                color = t.overlay_color(alpha)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, DOT / 2, DOT / 2)

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position())
        if idx != self._hover:
            self._hover = idx
            self.update()
            if idx is None:
                QToolTip.hideText()
            else:
                QToolTip.showText(
                    event.globalPosition().toPoint(), self._pages[idx]["name"], self
                )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        idx = self._index_at(event.position())
        if event.button() == Qt.LeftButton and idx is not None:
            self.page_clicked.emit(self._pages[idx]["id"])
            event.accept()
            return
        event.ignore()  # 점 사이 빈 곳은 위젯 창 이동으로 넘긴다


class _PageName(QLabel):
    """지금 페이지 이름 (넘치면 말줄임). 더블클릭하면 이름 바꾸기"""

    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.PlainText)
        # 긴 이름이 패널을 넓히지 않게 폭은 레이아웃이 정한다
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full = ""

    def set_full_text(self, text: str):
        self._full = text
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, self.width())
        self.setText(shown)
        self.setToolTip(
            "더블클릭하여 이름 바꾸기"
            if shown == self._full
            else f"{self._full}\n더블클릭하여 이름 바꾸기"
        )

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()
        event.accept()


class PageBar(QWidget):
    """[지금 페이지 이름] [점들] [+] 한 줄 (왼쪽 / 오른쪽 배치에서는 세로로 점과 + 만)"""

    page_selected = Signal(int)  # 점을 누름 - 페이지 id
    step_requested = Signal(int)  # 휠 - 앞(-1) / 뒤(+1) 페이지
    add_requested = Signal()
    rename_requested = Signal()
    move_requested = Signal(int)  # 지금 페이지를 앞(-1) / 뒤(+1)로
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._current = None

        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 4, 0)
        self._layout.setSpacing(4)

        self.name_label = _PageName(self)
        self.name_label.double_clicked.connect(self.rename_requested.emit)
        self.dots = PageDots(self)
        self.dots.page_clicked.connect(self.page_selected.emit)
        self.btn_add = QPushButton("+", self)
        self.btn_add.setObjectName("pageAdd")
        self.btn_add.setFixedSize(ADD_BUTTON_SIZE, ADD_BUTTON_SIZE)
        self.btn_add.setFocusPolicy(Qt.NoFocus)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setToolTip("새 페이지")
        self.btn_add.clicked.connect(self.add_requested.emit)

        self._layout.addWidget(self.name_label, 1)
        self._layout.addWidget(self.dots, 0, Qt.AlignCenter)
        self._layout.addWidget(self.btn_add, 0, Qt.AlignCenter)
        # 세로 배치에서 점을 위로 붙인다 (가로에서는 이름이 남는 폭을 받는다)
        self._layout.addStretch(0)

    def set_vertical(self, vertical: bool):
        """왼쪽 / 오른쪽 배치: 세로로 점과 + 만 (이름은 점의 툴팁)"""
        self._layout.setDirection(
            QBoxLayout.TopToBottom if vertical else QBoxLayout.LeftToRight
        )
        # 가로일 때 오른쪽 4px 은 목록 행의 오른쪽 여백(스크롤바 자리)에 + 를 맞춘다
        self._layout.setContentsMargins(0, 0, 0 if vertical else 4, 0)
        self.name_label.setVisible(not vertical)
        self.dots.set_vertical(vertical)

    def set_pages(self, pages: list, current_id: int):
        self._pages = list(pages)
        self._current = current_id
        self.dots.set_pages(pages, current_id)
        name = next((page["name"] for page in pages if page["id"] == current_id), "")
        self.name_label.set_full_text(name)

    def apply_appearance(self):
        t = theme.current()
        self.name_label.setStyleSheet(
            f"font-size: {px(11, t.todo_scale)}px; font-weight: bold; color: {t.text_sub};"
        )
        self.dots.update()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy:
            self.step_requested.emit(-1 if dy > 0 else 1)
        event.accept()  # 목록이 스크롤되지 않게

    def contextMenuEvent(self, event):
        """지금 페이지 메뉴 (할 일 목록의 우클릭 메뉴로 올려 보내지 않는다)"""
        ids = [page["id"] for page in self._pages]
        idx = ids.index(self._current) if self._current in ids else 0
        menu = QMenu(self)
        menu.setStyleSheet(theme.menu_style(theme.current()))
        menu.addAction("새 페이지", self.add_requested.emit)
        menu.addAction("이름 바꾸기…", self.rename_requested.emit)
        menu.addSeparator()
        act_front = menu.addAction(
            "앞으로 옮기기", lambda: self.move_requested.emit(-1)
        )
        act_front.setEnabled(idx > 0)
        act_back = menu.addAction("뒤로 옮기기", lambda: self.move_requested.emit(1))
        act_back.setEnabled(idx < len(ids) - 1)
        menu.addSeparator()
        act_delete = menu.addAction("페이지 삭제…", self.delete_requested.emit)
        act_delete.setEnabled(len(ids) > 1)
        menu.exec(event.globalPos())

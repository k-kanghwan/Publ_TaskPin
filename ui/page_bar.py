"""TODO 페이지 표시 (우패널 위 / 아래 / 왼쪽 / 오른쪽 - 설정창 Appearance "페이지 표시 위치")

엑셀 시트처럼 페이지마다 독립된 할 일 목록을 둔다 (manager/todo_pages, TodoPanel).
이 줄은 보여주고 요청만 시그널로 올린다 ("멍청한 뷰").
  - 위 / 아래: [페이지 1][페이지 2][페이지 3] ... [점들][+]
    모든 페이지 이름 칩 - 지금 페이지는 강조색 테두리. 누르면 그 페이지로, 더블클릭하면 이름 바꾸기.
    칩이 폭을 넘치면 지금 페이지 칩이 보이게 옆으로 민다.
  - 왼쪽 / 오른쪽: 세로로 [점들][+]   (이름은 점의 툴팁)
  - 점: 지금 페이지는 강조색 알약, 나머지는 작은 점. 누르면 그 페이지로 (바뀔 때 알약이 옮겨 가며 늘었다 줄어든다)
  - 휠: 앞 / 뒤 페이지, 우클릭: 새 페이지 / 이름 바꾸기 / 앞·뒤로 옮기기 / 페이지 삭제
    (다른 페이지 칩에서 우클릭하면 그 페이지로 넘어간 뒤 메뉴를 띄운다)
"""

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
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
# 페이지 이름 칩 (위 / 아래 배치)
CHIP_PAD_H = 8  # 칩 안 좌우 여백(px)
CHIP_PAD_V = 1
CHIP_GAP = 4  # 칩 사이
CHIP_TEXT_MAX = 100  # 이름이 이보다 길면 말줄임(px) - 전체는 툴팁
CHIP_FADE = 18  # 칩이 넘칠 때 잘린 쪽 끝을 흐리게 지우는 폭(px)
CHIP_ALPHA = 45  # 다른 페이지 칩 테두리 (테마의 덧칠 색)
CHIP_HOVER_ALPHA = 110
CHIP_FONT_PX = 11  # 우패널 글자 배율을 곱한다


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


class PageTabs(QWidget):
    """모든 페이지 이름 칩 [페이지 1] [페이지 2] ... 지금 페이지는 강조색 테두리.
    누르면 그 페이지로, 더블클릭하면 이름 바꾸기. 칩이 폭을 넘치면 지금 페이지 칩이 보이게 옆으로 민다.
    둥근 테두리는 스타일시트(border-radius)가 아니라 직접 그린다 (배율에 따라 모서리가 깨지지 않게)."""

    page_clicked = Signal(int)  # 페이지 id
    page_double_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._current = None  # 지금 페이지 id
        self._hover = None  # 마우스가 올라간 칩 index
        self._offset = 0.0  # 넘칠 때 왼쪽으로 민 만큼(px)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        # 남는 폭은 받되, 칩이 많아도 패널을 넓히지 않는다 (minimumSizeHint 폭 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_pages(self, pages: list, current_id: int):
        self._pages = list(pages)
        self._current = current_id
        self.updateGeometry()
        self._keep_current_visible()
        self.update()

    def _names(self) -> list:
        """칩에 보일 이름 (길면 말줄임)"""
        metrics = self.fontMetrics()
        return [
            metrics.elidedText(page["name"], Qt.ElideRight, CHIP_TEXT_MAX)
            for page in self._pages
        ]

    def _chip_height(self) -> int:
        return self.fontMetrics().height() + CHIP_PAD_V * 2 + 2

    def _rects(self) -> list:
        """칩 자리 (민 만큼 옮기기 전)"""
        metrics = self.fontMetrics()
        rects, x = [], 0.5  # 1px 테두리가 흐려지지 않게 반 픽셀
        height = self._chip_height()
        top = (self.height() - height) / 2 + 0.5
        for name in self._names():
            width = metrics.horizontalAdvance(name) + CHIP_PAD_H * 2 + 2
            rects.append(QRectF(x, top, width - 1, height - 1))
            x += width + CHIP_GAP
        return rects

    def _total_width(self) -> int:
        rects = self._rects()
        return round(rects[-1].right() + 1) if rects else 0

    def sizeHint(self) -> QSize:
        return QSize(self._total_width(), self._chip_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._chip_height())

    def _keep_current_visible(self):
        """지금 페이지 칩이 다 보이도록 민다 (넘치지 않으면 0)"""
        ids = [page["id"] for page in self._pages]
        rects = self._rects()
        if self._current not in ids or not rects:
            self._offset = 0.0
            return
        rect = rects[ids.index(self._current)]
        width = self.width()
        if rect.right() + 1 - self._offset > width:
            self._offset = rect.right() + 1 - width
        if rect.left() - self._offset < 0:
            self._offset = rect.left() - 0.5
        self._offset = min(max(0.0, self._offset), max(0.0, self._total_width() - width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._keep_current_visible()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:  # 글자 배율이 바뀜
            self.updateGeometry()
            self._keep_current_visible()

    def page_at(self, pos):
        """pos(이 위젯 좌표)의 칩 페이지 id / 칩이 아니면 None"""
        idx = self._index_at(QPointF(pos))
        return self._pages[idx]["id"] if idx is not None else None

    def _index_at(self, pos):
        point = QPointF(pos.x() + self._offset, pos.y())
        for idx, rect in enumerate(self._rects()):
            if rect.adjusted(-CHIP_GAP / 2, -2, CHIP_GAP / 2, 2).contains(point):
                return idx
        return None

    def paintEvent(self, event):
        """칩을 따로 그린 뒤, 넘쳐서 잘린 쪽 끝을 흐리게 지워(더 있다는 표시) 위젯에 옮긴다."""
        ratio = self.devicePixelRatioF()
        canvas = QPixmap(
            max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio))
        )
        canvas.setDevicePixelRatio(ratio)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(-self._offset, 0)
        self._paint_chips(painter)
        painter.resetTransform()
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        width = self.width()
        if self._offset > 0:  # 왼쪽에 더 있다
            self._fade(painter, 0, CHIP_FADE)
        if self._total_width() - self._offset > width:  # 오른쪽에 더 있다
            self._fade(painter, width, width - CHIP_FADE)
        painter.end()
        QPainter(self).drawPixmap(0, 0, canvas)

    def _fade(self, painter: QPainter, clear_x: float, solid_x: float):
        """clear_x 에서 투명 -> solid_x 에서 그대로 (그 사이를 서서히 지운다)"""
        gradient = QLinearGradient(clear_x, 0, solid_x, 0)
        gradient.setColorAt(0, QColor(0, 0, 0, 0))
        gradient.setColorAt(1, QColor(0, 0, 0, 255))
        left = min(clear_x, solid_x)
        painter.fillRect(QRectF(left, 0, CHIP_FADE, self.height()), gradient)

    def _paint_chips(self, painter: QPainter):
        t = theme.current()
        painter.setFont(self.font())
        radius = self._chip_height() / 2
        for idx, (rect, name) in enumerate(zip(self._rects(), self._names())):
            current = self._pages[idx]["id"] == self._current
            hover = idx == self._hover
            if current:
                border, text = QColor(t.accent), t.text_main
            else:
                border = t.overlay_color(CHIP_HOVER_ALPHA if hover else CHIP_ALPHA)
                text = t.text_main if hover else t.text_sub
            painter.setPen(QPen(border, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(QColor(text))
            painter.drawText(rect, Qt.AlignCenter, name)

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position())
        if idx != self._hover:
            self._hover = idx
            self.update()
            # 줄인 이름은 툴팁으로 전체를 보여준다
            names = self._names()
            if idx is not None and names[idx] != self._pages[idx]["name"]:
                QToolTip.showText(
                    event.globalPosition().toPoint(), self._pages[idx]["name"], self
                )
            else:
                QToolTip.hideText()
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
        event.ignore()  # 칩 사이 빈 곳은 위젯 창 이동으로 넘긴다

    def mouseDoubleClickEvent(self, event):
        idx = self._index_at(event.position())
        if event.button() == Qt.LeftButton and idx is not None:
            self.page_double_clicked.emit(self._pages[idx]["id"])
            event.accept()
            return
        event.ignore()


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

        self.tabs = PageTabs(self)
        self.tabs.page_clicked.connect(self.page_selected.emit)
        self.tabs.page_double_clicked.connect(self._on_tab_double_clicked)
        self.dots = PageDots(self)
        self.dots.page_clicked.connect(self.page_selected.emit)
        self.btn_add = QPushButton("+", self)
        self.btn_add.setObjectName("pageAdd")
        self.btn_add.setFixedSize(ADD_BUTTON_SIZE, ADD_BUTTON_SIZE)
        self.btn_add.setFocusPolicy(Qt.NoFocus)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setToolTip("새 페이지")
        self.btn_add.clicked.connect(self.add_requested.emit)

        # 남는 폭은 칩 줄이 받는다 (칩은 왼쪽부터, 점과 + 는 오른쪽 끝)
        self._layout.addWidget(self.tabs, 1, Qt.AlignVCenter)
        self._layout.addWidget(self.dots, 0, Qt.AlignCenter)
        self._layout.addWidget(self.btn_add, 0, Qt.AlignCenter)
        # 세로 배치에서 점을 위로 붙인다 (가로에서는 칩 줄이 남는 폭을 받는다)
        self._layout.addStretch(0)

    def set_vertical(self, vertical: bool):
        """왼쪽 / 오른쪽 배치: 세로로 점과 + 만 (이름 칩은 숨기고 이름은 점의 툴팁)"""
        self._layout.setDirection(
            QBoxLayout.TopToBottom if vertical else QBoxLayout.LeftToRight
        )
        # 가로일 때 오른쪽 4px 은 목록 행의 오른쪽 여백(스크롤바 자리)에 + 를 맞춘다
        self._layout.setContentsMargins(0, 0, 0 if vertical else 4, 0)
        self.tabs.setVisible(not vertical)
        self.dots.set_vertical(vertical)

    def set_pages(self, pages: list, current_id: int):
        self._pages = list(pages)
        self._current = current_id
        self.dots.set_pages(pages, current_id)
        self.tabs.set_pages(pages, current_id)

    def apply_appearance(self):
        t = theme.current()
        font = QFont(self.font())
        font.setPixelSize(px(CHIP_FONT_PX, t.todo_scale))
        self.tabs.setFont(font)
        self.tabs.update()
        self.dots.update()

    def _on_tab_double_clicked(self, page_id: int):
        """칩 더블클릭: 그 페이지(첫 클릭에서 이미 넘어감)의 이름 바꾸기"""
        if page_id == self._current:
            self.rename_requested.emit()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy:
            self.step_requested.emit(-1 if dy > 0 else 1)
        event.accept()  # 목록이 스크롤되지 않게

    def contextMenuEvent(self, event):
        """지금 페이지 메뉴 (할 일 목록의 우클릭 메뉴로 올려 보내지 않는다).
        다른 페이지 칩 위에서 열면 그 페이지로 넘어간 뒤 그 페이지의 메뉴를 띄운다."""
        if self.tabs.isVisible():
            page_id = self.tabs.page_at(self.tabs.mapFromGlobal(event.globalPos()))
            if page_id is not None and page_id != self._current:
                self.page_selected.emit(page_id)  # set_pages 로 지금 페이지가 바뀐다
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

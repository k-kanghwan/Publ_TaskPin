"""TODO 페이지 표시 (우패널 위 / 아래 / 왼쪽 / 오른쪽 - 설정창 Appearance "페이지 표시 위치")

엑셀 시트처럼 페이지마다 독립된 할 일 목록을 둔다 (manager/todo_pages, TodoPanel).
이 줄은 보여주고 요청만 시그널로 올린다 ("멍청한 뷰").
  - 위 / 아래: [페이지 1][페이지 2][페이지 3] ... [점들][+]
    모든 페이지 이름 칩 - 지금 페이지는 강조색 테두리. 누르면 그 페이지로, 더블클릭하면 이름 바꾸기.
    이름 뒤에 그 페이지의 체크 안 한 할 일 수를 강조색 배지로 (0 이면 숨김, 구분선은 세지 않음).
    칩이 폭을 넘치면 지금 페이지 칩이 보이게 옆으로 민다.
  - 왼쪽 / 오른쪽: 세로로 [점들][+]   (이름은 점의 툴팁)
  - 점: 지금 페이지는 강조색 알약, 나머지는 작은 점. 누르면 그 페이지로 (바뀔 때 알약이 옮겨 가며 늘었다 줄어든다)
  - 칩을 끌면 브라우저 탭처럼 순서를 바꾼다 (나머지 칩이 비켜서고, 넘치면 끝에서 밀림, Esc 취소).
    점은 끌지 않는다.
  - 휠: 앞 / 뒤 페이지, 우클릭: 페이지 바로가기(모든 페이지 목록) / 새 페이지 / 이름 바꾸기 /
    앞·뒤로 옮기기 / 페이지 삭제 (다른 페이지 칩에서 우클릭하면 그 페이지로 넘어간 뒤 메뉴를 띄운다)
  - 고정 페이지(page["pinned"], 맨 앞 "미완료"): 칩 앞에 알람 시계, 끌 수 없고 다른 칩도 그 앞으로 못 간다.
    이름 바꾸기 / 옮기기 / 삭제 메뉴는 꺼진다. 점은 지금 페이지가 아니면 속이 빈 원.
"""

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QWidget,
)

from manager import todo_pages
from ui import painted, theme
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
CHIP_COUNT_GAP = 5  # 칩 안 이름 - 할 일 수 배지 간격(px)
COUNT_PAD_H = 4  # 할 일 수 배지 좌우 여백(px)
CHIP_SLIDE_MS = 120  # 칩을 끌 때 나머지 칩이 비켜서는 시간
DRAG_SCROLL_MS = 30  # 칩을 끌어 양 끝에 대면 이 간격으로 민다
DRAG_SCROLL_STEP = 6  # 한 번에 미는 폭(px)
PIN_ICON_GAP = 3  # 고정 칩: 알람 시계 - 이름 간격(px)


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
            if idx != self._current and self._pages[idx].get("pinned"):
                # 고정 페이지("미완료")는 속이 빈 원
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(color, 1.2))
                painter.drawEllipse(rect.adjusted(0.6, 0.6, -0.6, -0.6))
                painter.setPen(Qt.NoPen)
                continue
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
                page = self._pages[idx]
                tip = page["name"] + (f"\n{page['tip']}" if page.get("tip") else "")
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
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
    칩을 끌면 브라우저 탭처럼 커서를 따라가고 나머지 칩이 놓일 자리를 비켜 준다 (놓으면 page_moved).
    둥근 테두리는 스타일시트(border-radius)가 아니라 직접 그린다 (배율에 따라 모서리가 깨지지 않게)."""

    page_clicked = Signal(int)  # 페이지 id
    page_double_clicked = Signal(int)
    page_moved = Signal(int, int)  # 칩을 끌어 놓음 - 페이지 id, 새 index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._current = None  # 지금 페이지 id
        self._counts = {}  # 페이지 id -> 체크 안 한 할 일 수
        self._hover = None  # 마우스가 올라간 칩 index
        self._offset = 0.0  # 넘칠 때 왼쪽으로 민 만큼(px)
        # 칩 드래그
        # 드래그를 시작하기 전 누른 칩 (페이지 id, 누른 x - 내용 좌표, 누른 x - 위젯 좌표)
        self._press = None
        self._drag_id = None  # 끌고 있는 페이지 id
        self._drag_from = 0  # 끌기 시작한 index
        self._drag_slot = 0  # 지금 놓으면 갈 index
        self._drag_grab = 0.0  # 칩 왼쪽 끝 ~ 커서
        self._drag_x = 0.0  # 커서 x (이 위젯 좌표)
        self._slide_from = {}  # 페이지 id -> 비켜서기 시작한 x
        self._slide = 1.0  # 비켜서기 0 ~ 1
        self._slide_anim = QVariantAnimation(self)
        self._slide_anim.setDuration(CHIP_SLIDE_MS)
        self._slide_anim.setStartValue(0.0)
        self._slide_anim.setEndValue(1.0)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._slide_anim.valueChanged.connect(self._set_slide)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(DRAG_SCROLL_MS)
        self._scroll_timer.timeout.connect(self._auto_scroll)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        # 남는 폭은 받되, 칩이 많아도 패널을 넓히지 않는다 (minimumSizeHint 폭 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_pages(self, pages: list, current_id: int):
        self._pages = list(pages)
        self._current = current_id
        if self._drag_id is not None and self._drag_id not in self._ids():
            self._end_drag()  # 끄는 중에 그 페이지가 없어짐
        self._drag_slot = min(self._drag_slot, max(0, len(self._pages) - 1))
        self.updateGeometry()
        self._keep_current_visible()
        self.update()

    def set_counts(self, counts: dict):
        """페이지 id -> 체크 안 한 할 일 수. 바뀌었을 때만 다시 잰다 (할 일을 바꿀 때마다 부른다)"""
        if counts != self._counts:
            self._counts = dict(counts)
            self.updateGeometry()
            self._keep_current_visible()
            self.update()

    def _count_texts(self) -> list:
        """칩마다 할 일 수 글자 ("" 이면 표시 안 함)"""
        return [str(self._counts.get(page["id"]) or "") for page in self._pages]

    def _names(self) -> list:
        """칩에 보일 이름 (길면 말줄임)"""
        metrics = self.fontMetrics()
        return [
            metrics.elidedText(page["name"], Qt.ElideRight, CHIP_TEXT_MAX)
            for page in self._pages
        ]

    def _count_font(self):
        """할 일 수 배지 글꼴 - 이름보다 조금 작고 굵게"""
        font = QFont(self.font())
        font.setPixelSize(max(8, font.pixelSize() - 2))
        font.setBold(True)
        return font

    def _badge_width(self, count: str) -> float:
        return QFontMetrics(self._count_font()).horizontalAdvance(count) + COUNT_PAD_H * 2

    def _chip_height(self) -> int:
        return self.fontMetrics().height() + CHIP_PAD_V * 2 + 2

    def _ids(self) -> list:
        return [page["id"] for page in self._pages]

    def _pinned_count(self) -> int:
        """맨 앞에 고정된 페이지 수 (끌 수 없고 다른 칩이 그 앞으로 못 간다)"""
        count = 0
        for page in self._pages:
            if not page.get("pinned"):
                break
            count += 1
        return count

    def _pin_icon(self) -> int:
        """고정 칩 앞 알람 시계 크기(px) - 글자 높이에 맞춘다"""
        return max(8, self.fontMetrics().height() - 4)

    def _widths(self) -> dict:
        """페이지 id -> 칩 폭 (칩 사이 간격 제외)"""
        metrics = self.fontMetrics()
        widths = {}
        for page, name, count in zip(self._pages, self._names(), self._count_texts()):
            width = metrics.horizontalAdvance(name) + CHIP_PAD_H * 2 + 2
            if page.get("pinned"):
                width += self._pin_icon() + PIN_ICON_GAP
            if count:
                width += CHIP_COUNT_GAP + self._badge_width(count)
            widths[page["id"]] = width
        return widths

    @staticmethod
    def _lefts(order: list, widths: dict) -> dict:
        """order 순서로 늘어놓은 칩의 왼쪽 x (페이지 id -> x, 민 만큼 옮기기 전)"""
        lefts, x = {}, 0.5  # 1px 테두리가 흐려지지 않게 반 픽셀
        for page_id in order:
            lefts[page_id] = x
            x += widths[page_id] + CHIP_GAP
        return lefts

    def _rects(self) -> list:
        """칩 자리 (민 만큼 옮기기 전)"""
        ids, widths = self._ids(), self._widths()
        lefts = self._lefts(ids, widths)
        height = self._chip_height()
        top = (self.height() - height) / 2 + 0.5
        return [
            QRectF(lefts[page_id], top, widths[page_id] - 1, height - 1)
            for page_id in ids
        ]

    def _total_width(self) -> int:
        rects = self._rects()
        return round(rects[-1].right() + 1) if rects else 0

    def sizeHint(self) -> QSize:
        return QSize(self._total_width(), self._chip_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._chip_height())

    def _keep_current_visible(self):
        """지금 페이지 칩이 다 보이도록 민다 (넘치지 않으면 0). 칩을 끄는 중에는 그대로 둔다."""
        if self._drag_id is not None:
            return
        ids = self._ids()
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
        pinned = {page["id"] for page in self._pages if page.get("pinned")}
        chips = zip(self._ids(), self._rects(), self._names(), self._count_texts())
        if self._drag_id is None:
            for idx, (page_id, rect, name, count) in enumerate(chips):
                current = page_id == self._current
                self._paint_chip(
                    painter,
                    t,
                    rect,
                    name,
                    count,
                    current,
                    idx == self._hover,
                    pinned=page_id in pinned,
                )
            return
        # 끄는 중: 나머지 칩은 놓일 자리를 비켜 서고, 끄는 칩은 커서를 따라 맨 위에 (배경을 칠해 덮는다)
        lefts = self._shown_lefts()
        dragged = None
        for page_id, rect, name, count in chips:
            current = page_id == self._current
            if page_id == self._drag_id:
                rect.moveLeft(self._drag_left())
                dragged = (rect, name, count, current)
                continue
            rect.moveLeft(lefts[page_id])
            self._paint_chip(
                painter, t, rect, name, count, current, False, pinned=page_id in pinned
            )
        if dragged is not None:
            self._paint_chip(painter, t, *dragged, True, QColor(t.bg))

    def _paint_chip(
        self, painter, t, rect, name, count, current, hover, fill=None, pinned=False
    ):
        radius = self._chip_height() / 2
        if current:
            border, text = QColor(t.accent), t.text_main
        else:
            border = t.overlay_color(CHIP_HOVER_ALPHA if hover else CHIP_ALPHA)
            text = t.text_main if hover else t.text_sub
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill if fill is not None else Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)
        # 이름 + 할 일 수를 한 덩어리로 가운데에
        inner = rect.adjusted(CHIP_PAD_H + 0.5, 0, -(CHIP_PAD_H + 0.5), 0)
        if pinned:  # 고정 페이지("미완료"): 이름 앞에 알람 시계 (지금 페이지면 강조색)
            size = self._pin_icon()
            icon = painted.alarm_pixmap(
                t.accent if current else text, size, self.devicePixelRatioF()
            )
            top = rect.center().y() - size / 2
            painter.drawPixmap(QPointF(inner.left(), top), icon)
            inner.setLeft(inner.left() + size + PIN_ICON_GAP)
        painter.setPen(QColor(text))
        painter.drawText(inner, Qt.AlignLeft | Qt.AlignVCenter, name)
        if count:  # 오른쪽 끝에 강조색 알약 배지
            badge_h = rect.height() - 4
            badge = QRectF(
                inner.right() - self._badge_width(count),
                rect.center().y() - badge_h / 2,
                self._badge_width(count),
                badge_h,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t.accent) if current else t.overlay_color(60))
            painter.drawRoundedRect(badge, badge_h / 2, badge_h / 2)
            painter.setFont(self._count_font())
            painter.setPen(QColor(t.on_accent if current else t.text_main))
            painter.drawText(badge, Qt.AlignCenter, count)
            painter.setFont(self.font())

    # ---- 칩 드래그 (순서 바꾸기) ----
    def dragging(self) -> bool:
        return self._drag_id is not None

    def _drag_order(self) -> list:
        """끄는 칩을 지금 놓으면 될 순서"""
        return todo_pages.moved(self._ids(), self._drag_id, self._drag_slot)

    def _drag_left(self) -> float:
        """끄는 칩의 왼쪽 x (내용 좌표) - 커서를 따라가되 칩 줄 밖으로는 나가지 않는다"""
        widths = self._widths()
        right_most = 0.5 + sum(
            widths[page_id] + CHIP_GAP for page_id in widths if page_id != self._drag_id
        )
        # 고정 칩 앞으로는 가지 않는다
        left_most = 0.5 + sum(
            widths[page["id"]] + CHIP_GAP
            for page in self._pages[: self._pinned_count()]
        )
        left = self._drag_x + self._offset - self._drag_grab
        return min(max(left_most, left), right_most)

    def _shown_lefts(self) -> dict:
        """비켜서는 중인 칩들의 지금 x (페이지 id -> x)"""
        target = self._lefts(self._drag_order(), self._widths())
        if self._slide >= 1.0:
            return target
        return {
            page_id: self._slide_from.get(page_id, x)
            + (x - self._slide_from.get(page_id, x)) * self._slide
            for page_id, x in target.items()
        }

    def _set_slide(self, value):
        self._slide = value
        self.update()

    def _start_drag(self, x: float):
        page_id, press_x, _ = self._press
        self._press = None
        ids = self._ids()
        if page_id not in ids or ids.index(page_id) < self._pinned_count():
            return  # 고정 칩은 끌지 않는다
        widths = self._widths()
        left = self._lefts(ids, widths)[page_id]
        self._drag_id = page_id
        self._drag_from = self._drag_slot = ids.index(page_id)
        self._drag_grab = min(max(0.0, press_x - left), widths[page_id])
        self._slide_from, self._slide = {}, 1.0
        self._hover = None
        QToolTip.hideText()
        self.setCursor(Qt.ClosedHandCursor)
        self.grabKeyboard()  # Esc 로 취소
        self._scroll_timer.start()
        self._drag_to(x)

    def _drag_to(self, x: float):
        self._drag_x = x
        self._update_slot()
        self.update()

    def _update_slot(self):
        """끄는 칩이 쉬어 갈 자리 중 지금 칩 위치와 가장 가까운 곳으로 놓일 자리를 정한다
        (칩 폭이 달라도 반쯤 넘어가면 자리가 바뀐다). 바뀌면 나머지 칩이 비켜서기 시작한다."""
        ids, widths = self._ids(), self._widths()
        left = self._drag_left()
        slot = min(
            range(self._pinned_count(), len(ids)),  # 고정 칩 앞으로는 못 간다
            key=lambda s: abs(
                self._lefts(todo_pages.moved(ids, self._drag_id, s), widths)[
                    self._drag_id
                ]
                - left
            ),
        )
        if slot != self._drag_slot:
            self._slide_from = self._shown_lefts()
            self._drag_slot = slot
            self._slide = 0.0
            self._slide_anim.stop()
            self._slide_anim.start()

    def _auto_scroll(self):
        """칩이 넘칠 때 커서가 양 끝(흐린 곳)에 있으면 그쪽으로 민다"""
        width = self.width()
        limit = max(0.0, self._total_width() - width)
        step = 0
        if self._drag_x < CHIP_FADE:
            step = -DRAG_SCROLL_STEP
        elif self._drag_x > width - CHIP_FADE:
            step = DRAG_SCROLL_STEP
        offset = min(max(0.0, self._offset + step), limit)
        if offset != self._offset:
            self._offset = offset
            self._update_slot()
            self.update()

    def _end_drag(self):
        """드래그 끝 / 취소 (놓을지는 부르는 쪽이 정한다)"""
        self._press = None
        if self._drag_id is None:
            return
        self._drag_id = None
        self._scroll_timer.stop()
        self._slide_anim.stop()
        self._slide_from, self._slide = {}, 1.0
        self.releaseKeyboard()
        self.setCursor(Qt.PointingHandCursor)
        self._keep_current_visible()
        self.update()

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._drag_id is not None:
            self._drag_to(x)
            return
        if self._press is not None and (event.buttons() & Qt.LeftButton):
            if abs(x - self._press[2]) >= QApplication.startDragDistance():
                self._start_drag(x)
            return
        idx = self._index_at(event.position())
        if idx != self._hover:
            self._hover = idx
            self.update()
            # 줄인 이름은 툴팁으로 전체를 보여준다 (고정 페이지는 설명도)
            names = self._names()
            page = self._pages[idx] if idx is not None else None
            if page is not None and (names[idx] != page["name"] or page.get("tip")):
                tip = page["name"] + (f"\n{page['tip']}" if page.get("tip") else "")
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._drag_id is not None:
            event.accept()  # 끄는 중 다른 버튼
            return
        idx = self._index_at(event.position())
        if event.button() == Qt.LeftButton and idx is not None:
            page_id = self._pages[idx]["id"]
            x = event.position().x()
            # 넘어가면서(page_clicked) 칩 줄이 밀릴 수 있으니 내용 좌표는 먼저 잡아 둔다
            self._press = (page_id, x + self._offset, x)
            self.page_clicked.emit(page_id)
            event.accept()
            return
        event.ignore()  # 칩 사이 빈 곳은 위젯 창 이동으로 넘긴다

    def mouseReleaseEvent(self, event):
        if self._drag_id is not None and event.button() == Qt.LeftButton:
            page_id, slot, start = self._drag_id, self._drag_slot, self._drag_from
            self._end_drag()
            if slot != start:
                self.page_moved.emit(page_id, slot)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._press = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._drag_id is not None and event.key() == Qt.Key_Escape:
            self._end_drag()  # 취소 - 원래 순서 그대로
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:  # 글자 배율이 바뀜
            self.updateGeometry()
            self._keep_current_visible()
        elif event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self._end_drag()  # 끄는 중 다른 창으로 넘어감 - 놓음이 오지 않는다

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
    page_moved = Signal(int, int)  # 칩을 끌어 놓음 - 페이지 id, 새 index
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
        self.tabs.page_moved.connect(self.page_moved.emit)
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

    def set_counts(self, counts: dict):
        """페이지 id -> 체크 안 한 할 일 수 (이름 칩에 표시)"""
        self.tabs.set_counts(counts)

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
        if dy and not self.tabs.dragging():  # 칩을 끄는 중에는 넘기지 않는다
            self.step_requested.emit(-1 if dy > 0 else 1)
        event.accept()  # 목록이 스크롤되지 않게

    def contextMenuEvent(self, event):
        """지금 페이지 메뉴 (할 일 목록의 우클릭 메뉴로 올려 보내지 않는다).
        다른 페이지 칩 위에서 열면 그 페이지로 넘어간 뒤 그 페이지의 메뉴를 띄운다."""
        if self.tabs.dragging():
            event.accept()
            return
        if self.tabs.isVisible():
            page_id = self.tabs.page_at(self.tabs.mapFromGlobal(event.globalPos()))
            if page_id is not None and page_id != self._current:
                self.page_selected.emit(page_id)  # set_pages 로 지금 페이지가 바뀐다
        ids = [page["id"] for page in self._pages]
        idx = ids.index(self._current) if self._current in ids else 0
        pinned = self.tabs._pinned_count()
        fixed = idx < pinned  # 고정 페이지("미완료")는 이름 / 자리 / 삭제를 바꾸지 않는다
        menu = QMenu(self)
        menu.setStyleSheet(theme.menu_style(theme.current()))
        self._add_jump_menu(menu)
        menu.addSeparator()
        menu.addAction("새 페이지", self.add_requested.emit)
        act_rename = menu.addAction("이름 바꾸기…", self.rename_requested.emit)
        act_rename.setEnabled(not fixed)
        menu.addSeparator()
        act_front = menu.addAction(
            "앞으로 옮기기", lambda: self.move_requested.emit(-1)
        )
        act_front.setEnabled(idx > pinned)
        act_back = menu.addAction("뒤로 옮기기", lambda: self.move_requested.emit(1))
        act_back.setEnabled(not fixed and idx < len(ids) - 1)
        menu.addSeparator()
        act_delete = menu.addAction("페이지 삭제…", self.delete_requested.emit)
        act_delete.setEnabled(not fixed and len(ids) - pinned > 1)
        menu.exec(event.globalPos())

    def _add_jump_menu(self, menu: QMenu):
        """우클릭 "페이지 바로가기" 서브메뉴: 모든 페이지 (지금 페이지는 체크, 체크 안 한 할 일 수)"""
        # menu.addMenu("제목") 으로 만든 서브메뉴는 이 함수가 끝나면 PySide 가 지워 버린다 - 부모를 준다
        jump = QMenu("페이지 바로가기", menu)
        menu.addMenu(jump)
        jump.setStyleSheet(menu.styleSheet())
        for page in self._pages:
            count = self.tabs._counts.get(page["id"])
            label = page["name"] + (f"  ({count})" if count else "")
            action = jump.addAction(
                label.replace("&", "&&"),  # & 는 메뉴 단축 글자 표시가 되므로
                lambda _=False, pid=page["id"]: self.page_selected.emit(pid),
            )
            if page["id"] == self._current:
                action.setCheckable(True)
                action.setChecked(True)

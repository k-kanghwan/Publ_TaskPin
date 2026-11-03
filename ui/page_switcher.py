"""TODO 페이지 바로가기 창 (설정 단축키, 기본 F5)

페이지 이름으로 찾아 고른 페이지로 넘어간다. 위젯 테마의 확인 창(TagDialog / ConfirmDialog)과 같은 모양
(프레임 없는 둥근 배경 + 강조색 테두리). 목록은 직접 그린다 - 고른 행은 덧칠 둥근 사각형, 지금 페이지는
강조색 글자, 고정 페이지("미완료")는 알람 시계, 오른쪽에 체크 안 한 할 일 수 배지(페이지 칩과 같은 규칙).

검색은 조합 중인 한글까지 바로 거른다 (공백으로 나눈 단어가 모두 이름에 들어 있어야 맞음, 대소문자 무시).
처음에는 지금 페이지 다음 페이지를 골라 둔다 (F5 → Enter 로 바로 옆 페이지).

키보드
  - ↑ / ↓ / PgUp / PgDn : 고르기, Enter : 이동, Esc : 닫기
"""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui import painted, theme
from ui.text_input import PreeditLineEdit
from ui.theme import CORNER_RADIUS

DIALOG_WIDTH = 280
FONT_PX = 12
ROW_PAD_V = 5  # 행 위아래 여백(px)
ROW_PAD_H = 8
ROW_RADIUS = 4
MAX_ROWS = 9  # 이보다 많으면 스크롤
ICON_GAP = 6  # 알람 시계 자리 - 이름 간격
BADGE_PAD_H = 4  # 할 일 수 배지 좌우 여백
BADGE_GAP = 8  # 이름 - 배지 간격
HOVER_ALPHA = 22  # 마우스를 올린 행 (테마의 덧칠 색)
SELECT_ALPHA = 48  # 고른 행
EMPTY_TEXT = "일치하는 페이지가 없습니다"


def matches(name: str, query: str) -> bool:
    """공백으로 나눈 검색어 단어가 모두 이름에 들어 있는지 (대소문자 무시, 빈 검색어는 모두 맞음)"""
    name = name.casefold()
    return all(word in name for word in query.casefold().split())


class _PageList(QWidget):
    """직접 그리는 페이지 목록. 행을 누르면 activated"""

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # [{"id", "name", "pinned", "count"}]
        self._current = None  # 지금 페이지 id
        self._selected = -1
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def row_height(self) -> int:
        return self.fontMetrics().height() + ROW_PAD_V * 2

    def set_rows(self, rows: list, current_id, selected: int):
        self._rows = rows
        self._current = current_id
        self._selected = selected
        self._hover = -1
        self.setFixedHeight(max(1, len(rows)) * self.row_height())
        self.update()

    def selected(self) -> int:
        return self._selected

    def set_selected(self, idx: int):
        if self._rows:
            self._selected = min(max(0, idx), len(self._rows) - 1)
            self.update()

    def selected_rect(self) -> QRectF:
        h = self.row_height()
        return QRectF(0, self._selected * h, self.width(), h)

    def _index_at(self, y: float) -> int:
        idx = int(y // self.row_height())
        return idx if 0 <= idx < len(self._rows) else -1

    def _badge_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(8, font.pixelSize() - 1))
        font.setBold(True)
        return font

    def paintEvent(self, event):
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        metrics = self.fontMetrics()
        badge_metrics = QFontMetrics(self._badge_font())
        h = self.row_height()
        icon_size = max(8, metrics.height() - 4)
        for idx, row in enumerate(self._rows):
            rect = QRectF(0.5, idx * h + 0.5, self.width() - 1, h - 1)
            alpha = (
                SELECT_ALPHA
                if idx == self._selected
                else HOVER_ALPHA if idx == self._hover else 0
            )
            if alpha:
                path = QPainterPath()
                path.addRoundedRect(rect, ROW_RADIUS, ROW_RADIUS)
                painter.fillPath(path, t.overlay_color(alpha))
            current = row["id"] == self._current
            inner = rect.adjusted(ROW_PAD_H, 0, -ROW_PAD_H, 0)
            # 알람 시계 자리는 모든 행에 비워 두어 이름이 같은 줄에서 시작하게
            if row.get("pinned"):
                icon = painted.alarm_pixmap(
                    t.accent, icon_size, self.devicePixelRatioF()
                )
                painter.drawPixmap(
                    QPointF(inner.left(), rect.center().y() - icon_size / 2), icon
                )
            inner.setLeft(inner.left() + icon_size + ICON_GAP)
            count = str(row.get("count") or "")
            if count:
                width = badge_metrics.horizontalAdvance(count) + BADGE_PAD_H * 2
                badge_h = metrics.height() - 2
                badge = QRectF(
                    inner.right() - width,
                    rect.center().y() - badge_h / 2,
                    width,
                    badge_h,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(t.accent) if current else t.overlay_color(60))
                painter.drawRoundedRect(badge, badge_h / 2, badge_h / 2)
                painter.setFont(self._badge_font())
                painter.setPen(QColor(t.on_accent if current else t.text_main))
                painter.drawText(badge, Qt.AlignCenter, count)
                painter.setFont(self.font())
                inner.setRight(badge.left() - BADGE_GAP)
            name = metrics.elidedText(row["name"], Qt.ElideRight, int(inner.width()))
            painter.setPen(QColor(t.accent if current else t.text_main))
            painter.drawText(inner, Qt.AlignLeft | Qt.AlignVCenter, name)

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position().y())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        idx = self._index_at(event.position().y())
        if event.button() == Qt.LeftButton and idx >= 0:
            self.set_selected(idx)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        idx = self._index_at(event.position().y())
        if event.button() == Qt.LeftButton and idx >= 0 and idx == self._selected:
            self.activated.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PageSwitcher(QDialog):
    def __init__(self, pages: list, current_id, counts: dict, parent=None):
        """pages: [{"id", "name", "pinned"?}] (표시 순서), counts: 페이지 id -> 체크 안 한 할 일 수"""
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)
        self._pages = [dict(page, count=counts.get(page["id"], 0)) for page in pages]
        self._current = current_id
        self._shown = []  # 거른 행 (self._pages 의 dict)

        t = self._theme = theme.current()
        self.setStyleSheet(
            theme.popup_form_style(t)
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0px; }}
            QScrollBar::handle:vertical {{
                background: {t.overlay(50)};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            """
        )
        painted.set_boxes(self, painted.form_rules(t))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("페이지 바로가기")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        hint = QLabel("Enter 이동 · Esc 닫기")
        hint.setStyleSheet(f"font-size: 11px; color: {t.text_sub};")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(hint)
        root.addLayout(header)

        self.edit = PreeditLineEdit()
        self.edit.setPlaceholderText("페이지 이름 검색")
        self.edit.textChanged.connect(lambda _text: self._refilter())
        self.edit.preedit_changed.connect(self._refilter)
        self.edit.returnPressed.connect(self._accept_selected)
        self.edit.installEventFilter(self)
        root.addWidget(self.edit)

        self.list = _PageList()
        font = QFont(self.font())
        if t.font_family:
            font.setFamilies([t.font_family, font.family()])
        font.setPixelSize(FONT_PX)
        self.list.setFont(font)
        self.list.activated.connect(self._accept_selected)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll.setWidget(self.list)
        # 검색으로 줄어도 창 크기는 그대로 (가운데에 띄운 창이 들썩이지 않게)
        rows = min(max(1, len(self._pages)), MAX_ROWS)
        self.scroll.setFixedHeight(rows * self.list.row_height())
        root.addWidget(self.scroll)

        self.empty = QLabel(EMPTY_TEXT)
        self.empty.setStyleSheet(f"font-size: 12px; color: {t.text_sub};")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        root.addWidget(self.empty)

        self._refilter(first=self._next_index())

    def _next_index(self) -> int:
        """처음 고를 행: 지금 페이지 다음 (마지막이면 앞 페이지)"""
        ids = [page["id"] for page in self._pages]
        if self._current not in ids:
            return 0
        idx = ids.index(self._current)
        return idx + 1 if idx + 1 < len(ids) else max(0, idx - 1)

    def _refilter(self, first: int = 0):
        query = self.edit.full_text()
        self._shown = [page for page in self._pages if matches(page["name"], query)]
        self.list.set_rows(self._shown, self._current, first if self._shown else -1)
        self.empty.setVisible(not self._shown)
        self.scroll.setVisible(bool(self._shown))
        self._keep_selected_visible()

    def _keep_selected_visible(self):
        if self.list.selected() >= 0:
            rect = self.list.selected_rect()
            self.scroll.ensureVisible(
                0, int(rect.center().y()), 0, int(rect.height() / 2) + 1
            )

    def _move(self, step: int):
        if self._shown:
            self.list.set_selected(self.list.selected() + step)
            self._keep_selected_visible()

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.KeyPress:
            steps = {
                Qt.Key_Up: -1,
                Qt.Key_Down: 1,
                Qt.Key_PageUp: -MAX_ROWS,
                Qt.Key_PageDown: MAX_ROWS,
            }
            if event.key() in steps:
                self._move(steps[event.key()])
                return True
        return super().eventFilter(obj, event)

    def _accept_selected(self):
        if self.list.selected() >= 0:
            self.accept()

    def page_id(self):
        """고른 페이지 id (거른 결과가 없으면 None)"""
        idx = self.list.selected()
        return self._shown[idx]["id"] if 0 <= idx < len(self._shown) else None

    def paintEvent(self, event):
        # 반투명 최상위 창은 스타일시트 배경이 그려지지 않으므로 직접 그린다
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CORNER_RADIUS,
            CORNER_RADIUS,
        )
        painter.fillPath(path, QColor(self._theme.dialog_bg))
        painter.setPen(QColor(self._theme.accent))
        painter.drawPath(path)

    def exec_over(self, anchor: QWidget) -> bool:
        """anchor 가운데에 띄우고(화면 안쪽으로 맞춤) 검색칸에 커서를 둔 뒤 결과를 돌려준다."""
        self.adjustSize()
        center = anchor.mapToGlobal(anchor.rect().center())
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(
            max(center.x() - self.width() // 2, area.left()),
            area.right() + 1 - self.width(),
        )
        y = min(
            max(center.y() - self.height() // 2, area.top()),
            area.bottom() + 1 - self.height(),
        )
        self.move(QPoint(x, y))
        self.edit.setFocus()
        return self.exec() == QDialog.Accepted and self.page_id() is not None

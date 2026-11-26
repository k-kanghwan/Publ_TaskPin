"""Windows 11 느낌의 우클릭 메뉴 (앱 전체 QProxyStyle) + 메뉴 아이콘

예전에는 메뉴마다 스타일시트(theme.menu_style)를 걸었지만, 스타일시트의 border-radius 는 안티앨리어싱 없이
그려져 둥근 hover 가 깨지고 아이콘 칸 / 단축키 칸을 맞추기 어렵다. 그래서 메뉴만 이 스타일이 직접 그린다.

- MenuStyle: TaskPin.py 의 __main__ 에서 앱 스타일로 건다 (바탕은 원래 앱 스타일 - windows11).
  메뉴 요소(패널 / 항목 / 구분선 / 빈 곳)만 그리고 나머지는 바탕 스타일에 맡긴다.
  색은 theme.current() 의 메뉴 색(MENU_FIELDS - 배경색과 관계없이 다크 / 라이트 설정을 따름)과 강조색.
  - 항목: 좌우 4px 안쪽의 둥근 hover, 16px 아이콘 칸(체크 항목은 ✓), 글자, 탭(\\t) 뒤 단축키는 흐리게 오른쪽,
    서브메뉴는 오른쪽 꺾쇠, 사용 불가는 흐린 색
  - menu.setProperty(CHECK_RING, True): 체크 대신 강조색 테두리로 고른 칸을 감싼다 (태그 메뉴)
  - Windows 11 이면 메뉴가 뜰 때 시스템 둥근 모서리 + 그림자 + 테두리 색 (os_win.round_popup), 아니면 사각 + 1px 테두리
  - 스타일시트에 QMenu 규칙이 있으면 이 스타일 대신 스타일시트가 그린다 - 메뉴 규칙은 두지 않는다.
- icon(name): Segoe Fluent Icons(없으면 Segoe MDL2 Assets) 글리프 아이콘. 그릴 때 지금 테마 색을 읽어
  트레이 메뉴처럼 오래 사는 메뉴도 테마를 따른다. 글꼴이 없으면 빈 아이콘(글자만).
"""

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QIconEngine,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QProxyStyle, QStyle, QStyleOptionMenuItem

from manager import os_win
from ui import theme

CHECK_RING = "checkRing"  # 메뉴 속성: 체크 항목을 ✓ 대신 강조색 테두리로 (태그 메뉴)

ITEM_HEIGHT = 30  # 항목 높이(px) - 글자가 크면 더 커진다
ITEM_PAD_V = 10  # 글자 위아래 여백 합
SEPARATOR_HEIGHT = 9
MENU_MARGIN = 4  # 메뉴 테두리 - 항목 사이
ITEM_RADIUS = 4  # 항목 hover 둥근 모서리
PAD_X = 10  # 항목 hover 안 좌우 여백
ICON_SIZE = 16
ICON_GAP = 10  # 아이콘 칸 - 글자
SHORTCUT_GAP = 28  # 글자 - 단축키
ARROW_WIDTH = 14  # 서브메뉴 꺾쇠 칸
ARROW_SIZE = 3.5  # 꺾쇠 반 높이(px)
CHECK_RING_WIDTH = 1.2

ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
# 이름 -> 글리프 (Segoe Fluent Icons / MDL2 Assets 공통 코드포인트)
GLYPHS = {
    "search": "",
    "cut": "",
    "copy": "",
    "paste": "",
    "delete": "",
    "add": "",
    "settings": "",
    "tag": "",
    "history": "",
    "undo": "",
    "redo": "",
    "folder": "",
    "lock": "",
    "pin": "",
    "power": "",
    "check": "",
    "rename": "",
    "move": "",
    "export": "",
    "import": "",
    "page": "",
    "page_add": "",
    "pages": "",
    "hide": "",
    "show": "",
    "rotate": "",
    "profile": "",
    "save": "",
    "collapse": "",
    "expand": "",
    "line": "",
    "clean": "",
    "clock": "",
    "open": "",
    "back": "",
    "forward": "",
    "startup": "",
    "close": "",
}

_family = None  # 찾은 아이콘 글꼴 ("" 이면 없음)
_icons = {}  # 이름 -> QIcon (엔진을 살려 둔다)


def _icon_family() -> str:
    global _family
    if _family is None:
        families = set(QFontDatabase.families())
        _family = next((name for name in ICON_FONTS if name in families), "")
    return _family


def _rgba(value: str) -> QColor:
    """테마 색 "#rrggbb" / "rgba(r,g,b,a)" -> QColor (테마의 메뉴 색은 둘 다 쓴다)"""
    if value.startswith("rgba("):
        r, g, b, a = (int(v) for v in value[5:-1].split(","))
        return QColor(r, g, b, a)
    return QColor(value)


class _GlyphEngine(QIconEngine):
    """글리프 아이콘 - 그릴 때마다 지금 테마의 메뉴 글자색(사용 불가면 흐린 색)으로. 벡터라 배율에 관계없이 선명하다."""

    def __init__(self, glyph: str):
        super().__init__()
        self._glyph = glyph

    def paint(self, painter, rect, mode, state):
        family = _icon_family()
        if not family:
            return
        t = theme.current()
        color = t.menu_disabled if mode == QIcon.Disabled else t.menu_text
        font = QFont(family)
        font.setPixelSize(max(8, round(min(rect.width(), rect.height()))))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(_rgba(color))
        painter.drawText(rect, Qt.AlignCenter, self._glyph)
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pixmap

    def clone(self):
        return _GlyphEngine(self._glyph)


def icon(name: str) -> QIcon:
    """메뉴 아이콘 (GLYPHS 의 이름). 아이콘 글꼴이 없으면 빈 아이콘"""
    cached = _icons.get(name)
    if cached is None:
        engine = _GlyphEngine(GLYPHS[name])
        cached = _icons[name] = QIcon(engine)
        cached._engine = engine  # 파이썬 엔진 객체를 QIcon 과 함께 살려 둔다
    return cached


class _MenuShowFilter(QObject):
    """메뉴가 뜰 때(창 핸들이 생긴 뒤) Windows 11 둥근 모서리 / 테두리 색을 건다"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QMenu):
            os_win.round_popup(
                int(obj.winId()), _rgba(theme.current().menu_border).name()
            )
        return False


class MenuStyle(QProxyStyle):
    """메뉴만 직접 그리는 앱 스타일 (나머지는 바탕 스타일)"""

    def __init__(self, base=None):
        super().__init__(base)
        self._show_filter = _MenuShowFilter()
        self._native_round = os_win.rounded_corners_supported()

    # ---- 크기 ----
    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PM_MenuHMargin, QStyle.PM_MenuVMargin):
            return MENU_MARGIN
        if metric == QStyle.PM_MenuPanelWidth:
            return 1
        if metric == QStyle.PM_SubMenuOverlap:
            return 0
        if metric == QStyle.PM_SmallIconSize and isinstance(widget, QMenu):
            return ICON_SIZE
        return super().pixelMetric(metric, option, widget)

    def sizeFromContents(self, contents, option, size, widget=None):
        if contents == QStyle.CT_MenuItem and isinstance(option, QStyleOptionMenuItem):
            if option.menuItemType == QStyleOptionMenuItem.Separator:
                return QSize(size.width(), SEPARATOR_HEIGHT)
            # size 는 단축키를 뺀 글자 크기 - 단축키 칸(tabWidth)은 QMenu 가 따로 더한다
            width = PAD_X + ICON_SIZE + ICON_GAP + size.width() + ARROW_WIDTH + PAD_X
            if "\t" in option.text:
                width += SHORTCUT_GAP
            height = max(ITEM_HEIGHT, size.height() + ITEM_PAD_V)
            return QSize(width, height)
        return super().sizeFromContents(contents, option, size, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_Menu_Scrollable:
            return 1
        return super().styleHint(hint, option, widget, returnData)

    # ---- 메뉴가 만들어질 때 ----
    def polish(self, arg):
        result = super().polish(arg)
        if isinstance(arg, QMenu):
            # 바탕 스타일이 반투명 / 그림자 효과를 걸면 시스템 둥근 모서리와 겹쳐 어색하다 - 불투명 창으로
            arg.setAttribute(Qt.WA_TranslucentBackground, False)
            arg.setGraphicsEffect(None)
            arg.removeEventFilter(self._show_filter)
            arg.installEventFilter(self._show_filter)
        return result

    # ---- 그리기 ----
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_PanelMenu:
            painter.fillRect(option.rect, _rgba(theme.current().menu_bg))
            return
        if element == QStyle.PE_FrameMenu:
            # Windows 11 은 시스템이 둥근 테두리를 그린다 (round_popup)
            if not self._native_round:
                painter.save()
                painter.setPen(QPen(_rgba(theme.current().menu_border), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
                painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)

    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.CE_MenuEmptyArea:
            painter.fillRect(option.rect, _rgba(theme.current().menu_bg))
            return
        if element == QStyle.CE_MenuItem and isinstance(option, QStyleOptionMenuItem):
            self._draw_item(option, painter, widget)
            return
        super().drawControl(element, option, painter, widget)

    def _draw_item(self, option, painter, widget):
        t = theme.current()
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(option.rect, _rgba(t.menu_bg))
        if option.menuItemType == QStyleOptionMenuItem.Separator:
            y = rect.center().y() + 0.5
            painter.setPen(QPen(_rgba(t.menu_border), 1))
            painter.drawLine(QPointF(rect.left() + 4, y), QPointF(rect.right() - 4, y))
            painter.restore()
            return
        enabled = bool(option.state & QStyle.State_Enabled)
        selected = enabled and bool(option.state & QStyle.State_Selected)
        checked = (
            option.checkType != QStyleOptionMenuItem.NotCheckable and option.checked
        )
        ring = checked and widget is not None and bool(widget.property(CHECK_RING))
        item = rect.adjusted(0, 1, 0, -1)
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(_rgba(t.menu_hover))
            painter.drawRoundedRect(item, ITEM_RADIUS, ITEM_RADIUS)
        if ring:  # 태그 메뉴: 고른 칸을 강조색 테두리로
            painter.setPen(QPen(QColor(t.accent), CHECK_RING_WIDTH))
            painter.setBrush(Qt.NoBrush)
            half = CHECK_RING_WIDTH / 2
            painter.drawRoundedRect(
                item.adjusted(half, half, -half, -half), ITEM_RADIUS, ITEM_RADIUS
            )

        text_color = _rgba(t.menu_text if enabled else t.menu_disabled)
        # 아이콘 칸: 체크 항목은 ✓ (아이콘이 있어도), 아니면 아이콘
        icon_rect = QRect(
            round(rect.left() + PAD_X),
            round(rect.center().y() - ICON_SIZE / 2),
            ICON_SIZE,
            ICON_SIZE,
        )
        if checked and not ring:
            self._draw_check(
                painter, QRectF(icon_rect), QColor(t.accent) if enabled else text_color
            )
        elif not option.icon.isNull():
            mode = QIcon.Normal if enabled else QIcon.Disabled
            option.icon.paint(painter, icon_rect, Qt.AlignCenter, mode)

        # 글자 / 단축키
        text, _, shortcut = option.text.partition("\t")
        left = rect.left() + PAD_X + ICON_SIZE + ICON_GAP
        right = rect.right() - PAD_X - ARROW_WIDTH
        text_rect = QRectF(left, rect.top(), right - left, rect.height())
        painter.setFont(option.font)
        painter.setPen(text_color)
        flags = Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic | Qt.TextSingleLine
        painter.drawText(text_rect, flags, text)
        if shortcut:
            painter.setPen(_rgba(t.menu_disabled))
            painter.drawText(
                text_rect, Qt.AlignVCenter | Qt.AlignRight | Qt.TextSingleLine, shortcut
            )
        if option.menuItemType == QStyleOptionMenuItem.SubMenu:
            self._draw_arrow(painter, rect, text_color)
        painter.restore()

    @staticmethod
    def _draw_check(painter, rect: QRectF, color: QColor):
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        w, h = rect.width(), rect.height()
        painter.drawPolyline(
            [
                QPointF(rect.left() + w * 0.2, rect.top() + h * 0.52),
                QPointF(rect.left() + w * 0.42, rect.top() + h * 0.74),
                QPointF(rect.left() + w * 0.8, rect.top() + h * 0.3),
            ]
        )

    @staticmethod
    def _draw_arrow(painter, rect: QRectF, color: QColor):
        """서브메뉴 꺾쇠 › (글꼴에 따라 글자 ▸ 가 깨지므로 직접 그린다)"""
        pen = QPen(color, 1.3)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        x = rect.right() - PAD_X - ARROW_WIDTH / 2 + ARROW_SIZE / 2
        y = rect.center().y()
        painter.drawPolyline(
            [
                QPointF(x - ARROW_SIZE, y - ARROW_SIZE * 1.6),
                QPointF(x, y),
                QPointF(x - ARROW_SIZE, y + ARROW_SIZE * 1.6),
            ]
        )

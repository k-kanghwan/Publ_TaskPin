"""안티앨리어싱으로 직접 그리는 부품

Qt 스타일시트의 border-radius 는 안티앨리어싱 없이 그려져 둥근 모서리가 계단처럼 깨진다
(화면 배율 125% / 150% 에서 특히 눈에 띈다). 그래서 둥근 부품은 QPainter 로 그린다.
크기 / 글꼴 / 글자색은 여전히 스타일시트(font-size, color, padding)를 따른다.

- CheckBox / EditableLabel : 직접 그리는 체크박스 / 더블클릭으로 고치는 이름 테두리
- set_boxes(root, 규칙) / set_box(위젯, Box) : 버튼 / 입력칸 / 배지 / 카드의 둥근 배경과 테두리.
  스타일시트는 배경을 transparent, 테두리를 같은 두께의 transparent 로 두고(글자 자리 유지)
  위젯이 그리기 전에(Paint 이벤트 필터) 상태(마우스 올림 / 누름 / 체크 / 포커스 / 사용 불가)에 맞는 색으로 칠한다.
- alarm_pixmap / alarm_img : 리마인더 알람 시계 아이콘 (⏰ 이모지 대신 - 강조색 등 테마 색으로 그린다)
- enter_pixmap : 할 일 입력칸 오른쪽의 Enter(↵) 아이콘
- draw_emoji_text / emoji_text_width / elide_emoji_text : 이모지만 키워 그리는 한 줄 글자 (작은 컬러 이모지는 깨짐)
"""

import math
from dataclasses import dataclass

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QObject,
    QPointF,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from manager import todo_store
from ui import theme

CHECK_BOX_PX = (
    14  # 체크박스 네모 (테두리 포함) - 글자 배율에 따라 set_box_size 로 바꾼다
)
CHECK_SPACING = 6  # 네모 - 글자 간격
EDITABLE_RADIUS = 4
CHECKED_BAR_WIDTH = 3  # Box.checked_bar 막대 폭


def _half_px(rect: QRectF) -> QRectF:
    """1px 선이 픽셀 경계에 걸쳐 흐려지지 않도록 반 픽셀 안쪽"""
    return rect.adjusted(0.5, 0.5, -0.5, -0.5)


class CheckBox(QCheckBox):
    """둥근 네모 + 체크 표시를 직접 그리는 체크박스. 글자가 있으면 네모 오른쪽에 쓴다."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._box = CHECK_BOX_PX
        self.setAttribute(Qt.WA_Hover, True)

    def set_box_size(self, size: int):
        if size != self._box:
            self._box = size
            self.updateGeometry()
            self.update()

    def sizeHint(self) -> QSize:
        if not self.text():
            return QSize(self._box, self._box)
        metrics = self.fontMetrics()
        return QSize(
            self._box + CHECK_SPACING + metrics.horizontalAdvance(self.text()),
            max(self._box, metrics.height()),
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)  # 글자를 눌러도 바뀌게

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.5)
        n = self._box
        box = QRectF(0, (self.height() - n) / 2, n, n)
        radius = max(2.0, n / 4.5)
        if self.isChecked():
            painter.setPen(QPen(QColor(t.accent), 1))
            painter.setBrush(QColor(t.accent))
            painter.drawRoundedRect(_half_px(box), radius, radius)
            mark = QPainterPath(box.topLeft() + QPointF(n * 0.26, n * 0.52))
            mark.lineTo(box.topLeft() + QPointF(n * 0.43, n * 0.69))
            mark.lineTo(box.topLeft() + QPointF(n * 0.75, n * 0.33))
            pen = QPen(QColor(t.on_accent), max(1.4, n / 9))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(mark)
        else:
            color = QColor(t.text_main) if self.underMouse() else t.overlay_color(130)
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(_half_px(box), radius, radius)
        if self.text():
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.setFont(self.font())
            text_rect = QRectF(self.rect()).adjusted(n + CHECK_SPACING, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())


class EditableLabel(QLabel):
    """더블클릭으로 고칠 수 있는 글자(사용자 이름 / TODO 페이지 이름). 둥근 테두리를 직접 그리고
    마우스를 올리면 진하게 한다. 테두리 두께 / 여백은 고칠 때 뜨는 편집칸과 같아 글자 자리가 그대로다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_Hover, True)

    def set_text_style(self, text_style: str):
        """글자 스타일(font-size / color 등). 테두리 자리(1px)는 투명하게 남기고 선은 paintEvent 가 그린다."""
        self.setStyleSheet(
            f"QLabel {{ {text_style} border: 1px solid transparent; padding: 0px 4px; }}"
        )

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(t.overlay_color(90 if self.underMouse() else 40), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            _half_px(QRectF(self.rect())), EDITABLE_RADIUS, EDITABLE_RADIUS
        )


# ==================================================
# 둥근 배경 / 테두리 (버튼 / 입력칸 / 배지 / 카드)
# ==================================================
@dataclass(frozen=True)
class Box:
    """위젯 뒤에 그릴 둥근 배경 + 테두리. 상태 색이 None 이면 평소 색을 쓴다(bg / border 가 None 이면
    그리지 않음). 사용 불가면 off_* 만, 아니면 누름 / 마우스 올림 -> 체크 -> 포커스 -> invalid 순으로 덮는다."""

    radius: float
    bg: QColor | None = None
    border: QColor | None = None
    width: float = 1  # 테두리 두께 - 스타일시트에도 같은 두께의 투명 테두리를 둔다
    hover_bg: QColor | None = None
    hover_border: QColor | None = None
    down_bg: QColor | None = None
    checked_bg: QColor | None = None
    checked_border: QColor | None = None
    checked_bar: QColor | None = None  # 체크하면 오른쪽 끝 막대 (설정창 왼쪽 탭)
    focus_border: QColor | None = None
    invalid_border: QColor | None = None  # property("invalid") 가 True 일 때
    off_bg: QColor | None = None
    off_border: QColor | None = None


def _color(value):
    if value is None or isinstance(value, QColor):
        return value
    return QColor(value)


def box(radius: float, bg=None, border=None, width: float = 1, **states) -> Box:
    """색은 QColor 또는 "#rrggbb" (반투명은 Theme.overlay_color 처럼 QColor 로)"""
    return Box(
        radius,
        _color(bg),
        _color(border),
        width,
        **{key: _color(value) for key, value in states.items()},
    )


def button_box(t: theme.Theme, radius: float = 6) -> Box:
    """theme.button_style 버튼"""
    return box(
        radius,
        t.overlay_color(26),
        t.overlay_color(40),
        hover_bg=t.overlay_color(46),
        down_bg=t.overlay_color(66),
        off_bg=t.overlay_color(10),
        off_border=t.overlay_color(18),
    )


def accent_box(t: theme.Theme, color: str = "", hover: str = "") -> Box:
    """확인 / 삭제처럼 색으로 채운 버튼 (기본: 강조색)"""
    color = color or t.accent
    hover = hover or t.accent_hover
    return box(
        6,
        color,
        color,
        hover_bg=hover,
        hover_border=hover,
        off_bg=t.overlay_color(10),
        off_border=t.overlay_color(18),
    )


def input_box(
    t: theme.Theme, radius: float = 6, border_alpha: int = 40, focus: bool = True
) -> Box:
    """입력칸. 포커스를 받으면 테두리를 진하게, property("invalid") 면 경고색"""
    return box(
        radius,
        t.overlay_color(18),
        t.overlay_color(border_alpha),
        focus_border=t.overlay_color(90) if focus else None,
        invalid_border=t.text_warn,
    )


def form_rules(t: theme.Theme) -> list:
    """theme.popup_form_style 의 입력칸 / 콤보박스 (set_boxes 규칙)"""
    return [
        (QLineEdit, None, input_box(t)),
        (QComboBox, None, input_box(t, focus=False)),
    ]


def _state_colors(widget: QWidget, look: Box):
    if not widget.isEnabled():
        return look.off_bg or look.bg, look.off_border or look.border
    bg, border = look.bg, look.border
    button = widget if isinstance(widget, QAbstractButton) else None
    if button is not None and button.isDown():
        bg = look.down_bg or look.hover_bg or bg
        border = look.hover_border or border
    elif widget.underMouse():
        bg = look.hover_bg or bg
        border = look.hover_border or border
    if button is not None and button.isChecked():  # 체크한 칸은 마우스를 올려도 체크 색
        bg = look.checked_bg or bg
        border = look.checked_border or border
    if look.focus_border is not None and widget.hasFocus():
        border = look.focus_border
    if look.invalid_border is not None and widget.property("invalid"):
        border = look.invalid_border
    return bg, border


def _paint_box(widget: QWidget, look: Box):
    bg, border = _state_colors(widget, look)
    bar = look.checked_bar
    if bar is not None and not (
        isinstance(widget, QAbstractButton) and widget.isChecked()
    ):
        bar = None
    if bg is None and border is None and bar is None:
        return
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(widget.rect())
    radius = look.radius
    if border is not None:
        # 선 가운데를 안쪽 width/2 에 둬서 바깥 반쪽이 잘리지 않게 (1px 선은 반 픽셀 안쪽 = 흐려지지 않음)
        inset = look.width / 2
        rect = rect.adjusted(inset, inset, -inset, -inset)
        radius = max(0.0, radius - inset)
        painter.setPen(QPen(border, look.width))
    else:
        painter.setPen(Qt.NoPen)
    painter.setBrush(bg if bg is not None else Qt.NoBrush)
    painter.drawRoundedRect(rect, radius, radius)
    if bar is not None:
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(widget.rect()), look.radius, look.radius)
        strip = QPainterPath()
        strip.addRect(
            QRectF(
                widget.width() - CHECKED_BAR_WIDTH,
                0,
                CHECKED_BAR_WIDTH,
                widget.height(),
            )
        )
        painter.fillPath(shape.intersected(strip), bar)


_BOX_EVENTS = (
    QEvent.Paint,
    QEvent.Enter,
    QEvent.Leave,
    QEvent.FocusIn,
    QEvent.FocusOut,
)


class _BoxPainter(QObject):
    """모양(Box)이 정해진 위젯마다 붙는 필터: 위젯이 스스로 그리기 전에(= 글자 아래에) 칠한다."""

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in _BOX_EVENTS:
            look = getattr(obj, "_painted_box", None)
            if look is not None:
                if kind == QEvent.Paint:
                    _paint_box(obj, look)
                else:
                    obj.update()  # 마우스 올림 / 포커스가 바뀌면 다시 그린다
        return False


class _Polisher(QObject):
    """앱 필터: 새 위젯이 준비(Polish)될 때 set_boxes 규칙을 찾아 모양을 붙인다
    (설정창 행 추가처럼 나중에 생기는 버튼 / 입력칸도 따르게)."""

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Polish and isinstance(obj, QWidget):
            _resolve(obj)
        elif kind == QEvent.ParentChange and isinstance(obj, QWidget):
            # 부모 없이 만들어 크기를 잰(= 이미 Polish 된) 뒤 레이아웃에 넣는 위젯은 이때 규칙을 찾는다
            # (그 위젯이 아직 Polish 전이어도 자식은 Polish 됐을 수 있다 - 설정창 행의 키 입력칸 등).
            # 아직 Polish 전인 위젯은 곧 Polish 때 찾으므로 건너뛴다 - 부모를 주고 만드는 위젯(목록 행 등)은
            # 자식이 없을 때 부모가 정해지므로 거의 비용이 들지 않는다
            for widget in [obj, *obj.findChildren(QWidget)]:
                if widget.testAttribute(Qt.WA_WState_Polished):
                    _resolve(widget)
        return False


_painter = None
_polisher = None


def _install():
    global _painter, _polisher
    if _painter is None:
        _painter = _BoxPainter()
        _polisher = _Polisher()
        QApplication.instance().installEventFilter(_polisher)


def _apply(widget: QWidget, look):
    if getattr(widget, "_painted_box", None) is look:
        return
    widget._painted_box = look
    if look is not None:
        widget.setAttribute(Qt.WA_Hover, True)
        widget.installEventFilter(_painter)  # 같은 필터는 다시 붙여도 한 번만 걸린다
    widget.update()


def _resolve(widget: QWidget):
    """widget 의 모양: set_box 로 정했으면 그대로, 아니면 가장 가까운 상위의 set_boxes 규칙 중 처음 맞는 것"""
    if getattr(widget, "_painted_own", False):
        return
    parent = widget.parentWidget()
    while parent is not None:
        rules = getattr(parent, "_painted_rules", None)
        if rules is not None:
            for cls, name, look in rules:
                if isinstance(widget, cls) and (
                    name is None or widget.objectName() == name
                ):
                    _apply(widget, look)
                    return
        parent = parent.parentWidget()
    if getattr(widget, "_painted_box", None) is not None:
        _apply(widget, None)


def set_boxes(root: QWidget, rules: list):
    """root 아래 위젯들의 모양 규칙 [(클래스, objectName 또는 None, Box 또는 None(그리지 않음))].
    위에서부터 처음 맞는 규칙을 쓰고, 가장 가까운 상위의 규칙이 먼저다. 나중에 생기는 위젯도 따른다.
    맞는 위젯의 스타일시트는 배경을 transparent, 테두리를 같은 두께의 transparent 로 둬야 한다.
    테마를 바꾸면 새 Box 로 다시 부른다."""
    _install()
    root._painted_rules = rules
    for widget in root.findChildren(QWidget):
        _resolve(widget)


def set_box(widget: QWidget, look):
    """이 위젯 하나의 모양 (규칙보다 먼저). None 이면 그리지 않는다."""
    _install()
    widget._painted_own = True
    _apply(widget, look)


# ==================================================
# 리마인더 알람 시계 아이콘
# ==================================================
_ALARM_URIS = {}  # (색, 크기, 배율) -> data URI (행마다 같은 그림을 다시 만들지 않게)


def alarm_pixmap(color: str, size: int, ratio: float = 1.0) -> QPixmap:
    """알람 시계: 둥근 시계판 + 바늘 + 위쪽 양옆의 종(시계판 둘레의 호) + 다리. 선 하나 색으로 그린다.
    ratio: 화면 배율 (그 배율의 실제 픽셀로 그려 흐리거나 깨지지 않게)"""
    n = float(size)
    pixmap = QPixmap(max(1, round(n * ratio)), max(1, round(n * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), max(1.2, n * 0.11))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    center = QPointF(n * 0.5, n * 0.56)
    face = n * 0.33
    painter.drawEllipse(center, face, face)
    painter.drawLine(center, center + QPointF(0, -face * 0.58))  # 분침 (12시)
    painter.drawLine(center, center + QPointF(face * 0.45, 0))  # 시침 (3시)

    # 종: 시계판 바깥 둘레의 짧은 호 (10시 반 / 1시 반 방향). 각도는 3시 방향부터 반시계, 1/16도
    ring = face + n * 0.17
    bound = QRectF(center.x() - ring, center.y() - ring, ring * 2, ring * 2)
    for start in (25, 120):
        painter.drawArc(bound, start * 16, 35 * 16)
    # 다리: 시계판 아래 양옆으로 짧게
    for degrees in (225, 315):
        angle = math.radians(degrees)
        direction = QPointF(math.cos(angle), -math.sin(angle))
        painter.drawLine(
            center + direction * (face + n * 0.02), center + direction * (face + n * 0.14)
        )
    painter.end()
    return pixmap


def alarm_img(color: str, size: int, ratio: float = 1.0) -> str:
    """RichText 라벨용 <img> (알람 시계, data URI). 크기는 논리 px"""
    key = (color, size, round(ratio, 2))
    uri = _ALARM_URIS.get(key)
    if uri is None:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        alarm_pixmap(color, size, ratio).toImage().save(buffer, "PNG")
        uri = "data:image/png;base64," + bytes(data.toBase64()).decode("ascii")
        _ALARM_URIS[key] = uri
    return f'<img src="{uri}" width="{size}" height="{size}">'


# ==================================================
# 할 일 입력칸 Enter 아이콘
# ==================================================
def enter_pixmap(color: str, size: int, ratio: float = 1.0) -> QPixmap:
    """Enter(↵) 아이콘: 오른쪽 위에서 내려와 왼쪽으로 꺾이는 둥근 선 + 화살촉. 선 하나 색으로 그린다.
    ratio: 화면 배율 (그 배율의 실제 픽셀로 그려 흐리거나 깨지지 않게)

    소수 좌표·두께로 그리면 1px 선이 두 픽셀에 걸쳐 번지므로, 장치 픽셀 단위로 계산해 선 가운데를
    픽셀 격자에 맞춘다 (두께가 홀수면 픽셀 가운데 +0.5). 화살촉은 꺾인 경로 하나로 그려 끝이 겹쳐
    진해지지 않게 한다."""
    dev = max(1, round(size * ratio))  # 장치 픽셀 한 변
    pixmap = QPixmap(dev, dev)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    # setDevicePixelRatio 한 pixmap 의 painter 는 논리 좌표라 장치 픽셀로 되돌려 그린다
    painter.scale(1 / ratio, 1 / ratio)
    width = max(1, round(1.5 * ratio))
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    half = 0.5 if width % 2 else 0.0

    def snap(v: float) -> float:
        return round(dev * v) + half

    right, top, bottom, left = snap(0.76), snap(0.2), snap(0.64), snap(0.2)
    corner = round(dev * 0.2)  # 꺾이는 곳의 둥근 반지름
    head = round(dev * 0.2)  # 화살촉
    path = QPainterPath(QPointF(right, top))
    path.lineTo(right, bottom - corner)
    path.quadTo(right, bottom, right - corner, bottom)
    path.lineTo(left, bottom)
    painter.drawPath(path)
    arrow = QPainterPath(QPointF(left + head, bottom - head))
    arrow.lineTo(left, bottom)
    arrow.lineTo(left + head, bottom + head)
    painter.drawPath(arrow)
    painter.end()
    return pixmap


# ==================================================
# 이모지를 키워 그리는 한 줄 글자 (페이지 칩 / 페이지 바로가기 창)
# ==================================================
# 작은 글자 크기(11~12px)의 컬러 이모지는 계단처럼 깨진다 - 할 일 행(todo_panel.EMOJI_PX)처럼 이모지만
# 글자보다 이만큼 키워 그린다
EMOJI_GROW_PX = 3


def _emoji_font(font: QFont) -> QFont:
    """글자보다 EMOJI_GROW_PX 큰 글꼴 (pt 로 정한 글꼴은 pixelSize() 가 -1 이라 실제 px 로 잰다)"""
    size = font.pixelSize() if font.pixelSize() > 0 else QFontInfo(font).pixelSize()
    emoji = QFont(font)
    emoji.setPixelSize(max(1, size) + EMOJI_GROW_PX)
    return emoji


def _emoji_units(text: str) -> list:
    """글자를 [(조각, 이모지인지)] 로 - 이모지 덩어리(ZWJ / 피부색 포함)는 한 조각"""
    units, pos = [], 0
    for match in todo_store.EMOJI_RE.finditer(text):
        units += [(ch, False) for ch in text[pos : match.start()]]
        units.append((match.group(), True))
        pos = match.end()
    units += [(ch, False) for ch in text[pos:]]
    return units


def _runs(units: list) -> list:
    """이웃한 같은 종류 조각을 묶는다 (글자는 한 번에 그려야 자간 / 커닝이 맞다)"""
    runs = []
    for part, is_emoji in units:
        if runs and runs[-1][1] == is_emoji:
            runs[-1] = (runs[-1][0] + part, is_emoji)
        else:
            runs.append((part, is_emoji))
    return runs


def emoji_text_width(font: QFont, text: str) -> float:
    """emoji_text 로 그렸을 때의 폭"""
    plain, emoji = QFontMetrics(font), QFontMetrics(_emoji_font(font))
    return sum(
        (emoji if is_emoji else plain).horizontalAdvance(part)
        for part, is_emoji in _runs(_emoji_units(text))
    )


def elide_emoji_text(font: QFont, text: str, width: float) -> str:
    """width 를 넘으면 뒤를 잘라 "…" 를 붙인다 (이모지 덩어리는 쪼개지 않는다)"""
    if emoji_text_width(font, text) <= width:
        return text
    units = _emoji_units(text)
    while units:
        units.pop()
        candidate = "".join(part for part, _ in units).rstrip() + "…"
        if emoji_text_width(font, candidate) <= width:
            return candidate
    return "…"


def draw_emoji_text(painter: QPainter, rect: QRectF, text: str, font: QFont):
    """rect 왼쪽부터 세로 가운데에 text 를 그린다 - 이모지만 EMOJI_GROW_PX 키워서 (색은 painter 의 펜)"""
    emoji_font = _emoji_font(font)
    x = rect.left()
    for part, is_emoji in _runs(_emoji_units(text)):
        use = emoji_font if is_emoji else font
        advance = QFontMetrics(use).horizontalAdvance(part)
        painter.setFont(use)
        painter.drawText(
            QRectF(x, rect.top(), advance + 1, rect.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            part,
        )
        x += advance
    painter.setFont(font)

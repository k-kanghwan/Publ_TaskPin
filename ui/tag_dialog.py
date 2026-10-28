"""TODO 사용자 태그 추가 창 (우패널 태그 메뉴 "+ 태그 추가…" / 설정창 Appearance)

이름과 색을 고른다. 색은 미리 고른 색 중에서 또는 "직접…" 으로 색 선택 창에서.
저장은 부르는 쪽이 한다(widget_config.add_custom_tag).
색 칸 없이(with_color=False) TODO 페이지 이름 바꾸기에도 쓴다.

키보드
  - Enter : 추가, Esc : 취소
"""

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from manager import widget_config
from ui import painted, theme
from ui.color_dialog import pick_color
from ui.theme import CORNER_RADIUS

DIALOG_WIDTH = 280
SWATCH_SIZE = 20
# 색 칸: 동그라미 / 테두리는 ui/painted 가 그린다 (같은 두께의 투명 테두리로 자리만)
_SWATCH_STYLE = "QPushButton { background: transparent; border: 2px solid transparent; padding: 0px; }"
# 기본 태그(Red ~ Gray)와 겹치지 않는 색 위주
PRESET_COLORS = [
    "#a77bd8",  # 보라
    "#e86fa4",  # 분홍
    "#3fa7a0",  # 청록
    "#63c7d8",  # 하늘
    "#5e6ad2",  # 남색
    "#a2845e",  # 갈색
    "#8bc34a",  # 연두
]


class TagDialog(QDialog):
    def __init__(
        self,
        title: str = "태그 추가",
        ok_text: str = "추가",
        name: str = "",
        color: str = "",
        with_color: bool = True,
        placeholder: str = "이름 (예: Work)",
        max_length: int = widget_config.CUSTOM_TAG_NAME_MAX,
        parent=None,
    ):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)
        self._color = color or PRESET_COLORS[0]

        t = self._theme = theme.current()
        self.setStyleSheet(
            theme.button_style(t)
            + theme.popup_form_style(t)
            + f"""
            QLabel {{
                background: transparent;
                color: {t.text_main};
                font-family: {t.font_family};
            }}
            QPushButton {{ padding: 6px 0px; }}
            QPushButton#ok {{ color: {t.on_accent}; font-weight: bold; }}
            QPushButton#ok:disabled {{ color: {t.text_disabled}; }}
            """
        )
        painted.set_boxes(
            self,
            [
                (QPushButton, "ok", painted.accent_box(t)),
                *painted.form_rules(t),
                (QPushButton, None, painted.button_box(t)),
            ],
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        root.addWidget(title_label)

        self.name_edit = QLineEdit(name)
        self.name_edit.setMaxLength(max_length)
        self.name_edit.setPlaceholderText(placeholder)
        self.name_edit.textChanged.connect(self._update_ok)
        root.addWidget(self.name_edit)

        # ---- 색 ----
        swatches = QWidget()
        row = QHBoxLayout(swatches)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._swatches = []
        for color in PRESET_COLORS:
            btn = self._swatch(color)
            btn.clicked.connect(lambda _=False, c=color: self._set_color(c))
            self._swatches.append((color, btn))
            row.addWidget(btn)
        self._custom = self._swatch("")
        self._custom.setToolTip("직접 선택")
        self._custom.clicked.connect(self._pick_custom)
        row.addWidget(self._custom)
        row.addStretch(1)
        root.addWidget(swatches)
        swatches.setVisible(with_color)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton(ok_text)
        self.btn_ok.setObjectName("ok")
        self.btn_ok.setDefault(True)  # Enter
        for btn in (btn_cancel, self.btn_ok):
            btn.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(btn)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        root.addSpacing(2)
        root.addLayout(buttons)

        self._paint_swatches()
        self._update_ok()

    def _swatch(self, color: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(color)
        return btn

    def _paint_swatches(self):
        """고른 색에 글자색 테두리. 미리 고른 색이 아니면 "직접 선택" 칸에 그 색을 칠한다."""
        t = self._theme
        radius = SWATCH_SIZE // 2
        for color, btn in self._swatches:
            ring = t.text_main if color == self._color else color
            btn.setStyleSheet(_SWATCH_STYLE)
            painted.set_box(btn, painted.box(radius, color, ring, width=2))
        custom = self._color not in PRESET_COLORS
        self._custom.setText("" if custom else "+")
        fill = self._color
        ring = t.text_main if custom else t.text_sub
        self._custom.setStyleSheet(
            _SWATCH_STYLE + f" QPushButton {{ color: {t.text_sub}; font-size: 12px; }}"
        )
        painted.set_box(
            self._custom, painted.box(radius, fill if custom else None, ring, width=2)
        )

    def _set_color(self, color: str):
        self._color = color
        self._paint_swatches()

    def _pick_custom(self):
        color = pick_color(self._color, "태그 색")
        if color:
            self._set_color(color)

    def _update_ok(self):
        self.btn_ok.setEnabled(bool(self.name_edit.text().strip()))

    def name(self) -> str:
        return self.name_edit.text().strip()

    def color(self) -> str:
        return self._color

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
        """anchor 가운데에 띄우고(화면 안쪽으로 맞춤) 이름 칸에 커서를 둔 뒤 결과를 돌려준다."""
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
        self.name_edit.setFocus()
        self.name_edit.selectAll()
        return self.exec() == QDialog.Accepted

"""설정창 (위젯 우클릭 "설정" / 설정 단축키 Ctrl+,)

좌측 사이드바에서 탭을 고르고 우측 카드에서 바로 바꾼다 (확인 버튼 없이 즉시 config.json 에 저장).
  - Keyboard Shortcuts : 위젯 단축키. 다른 동작과 겹치면 저장하지 않고 경고
  - Snippets           : `:트리거:` -> 문구 목록. 빈 칸 / 중복 트리거는 저장하지 않고 표시만
  - Appearance         : 테마 / 강조색 / 배경색 / 폰트, 좌·우패널 글자 크기, TODO 글자색.
                         바꾸면 appearance_changed 로 위젯에 바로 반영한다.
  - Application        : 준비 중

설정창 자체는 위젯 테마를 따르지 않고 다크로 고정한다.

키보드
  - Esc : 닫기 (단축키 입력칸에서는 입력 취소)
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from manager import os_win, snippets, widget_config
from ui import theme

_DARK = theme.DARK
ACCENT = _DARK.accent
FONT_FAMILY = _DARK.font_family
LINE_COLOR = _DARK.line
TEXT_MAIN = _DARK.text_main
TEXT_SUB = _DARK.text_sub
TEXT_WARN = _DARK.text_warn


WINDOW_TITLE = "Task알림 설정"
WINDOW_SIZE = (720, 560)  # Appearance 탭이 스크롤 없이 거의 다 보이도록
WINDOW_BG = "#18181a"
CARD_BG = "#232326"
CARD_BORDER = "rgba(255,255,255,22)"
SIDEBAR_WIDTH = 210
NAV_ICON_WIDTH = 22  # 기호마다 폭이 달라 탭 이름이 어긋나지 않도록 고정
KEY_EDIT_WIDTH = 120
TRIGGER_EDIT_WIDTH = 110
FONT_COMBO_WIDTH = 190
SWATCH_SIZE = 20
COLOR_CHIP_SIZE = 12

# (아이콘, 탭 이름) - 아이콘은 글자색을 따르는 흑백 기호
TABS = [
    ("⌨", "Keyboard Shortcuts"),
    ("✎", "Snippets"),
    ("◐", "Appearance"),
    ("▦", "Application"),
]

# (동작, 이름, 보조설명) - 동작 키는 widget_config.DEFAULT_SHORTCUTS 와 같다
SHORTCUT_ROWS = [
    ("task_register", "Task 등록", "Task 등록 창을 엽니다"),
    ("task_clear", "Task 해제", "등록한 Task를 해제합니다"),
    ("todo_focus", "할 일 추가", "할 일 입력칸으로 커서 이동"),
    ("settings", "설정 열기", "이 설정창을 엽니다"),
]

# Appearance 선택지 (값, 표시) - 값은 widget_config.THEMES / LEFT_SCALES / TODO_SCALES 와 같다
THEME_OPTIONS = [("dark", "다크"), ("light", "라이트"), ("system", "시스템")]
SCALE_NAMES = {90: "작게", 100: "보통", 115: "크게", 130: "아주 크게"}
ACCENT_SWATCHES = [
    ("#4a7bd0", "파랑"),
    ("#3fa7a0", "청록"),
    ("#5aa45e", "초록"),
    ("#e0a030", "주황"),
    ("#e57373", "빨강"),
    ("#a77bd8", "보라"),
    ("#8e8e93", "회색"),
]
DEFAULT_FONT_LABEL = "기본 (맑은 고딕)"

SETTINGS_STYLE = (
    theme.button_style(_DARK)
    + theme.popup_form_style(_DARK)
    + f"""
    QWidget#settings {{ background: {WINDOW_BG}; }}
    QLabel {{
        background: transparent;
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY};
        font-size: 13px;
    }}
    QLabel#sub {{ color: {TEXT_SUB}; font-size: 11px; }}
    QLabel#section {{ font-size: 14px; font-weight: bold; }}
    QLabel#navIcon {{ font-size: 15px; color: {TEXT_SUB}; }}
    QLabel#version {{
        color: {TEXT_SUB};
        font-weight: bold;
        border: 1px solid rgba(255,255,255,40);
        border-radius: 14px;
        padding: 6px;
    }}
    QFrame#card, QFrame#sidebar {{
        background: {CARD_BG};
        border: 1px solid {CARD_BORDER};
        border-radius: 14px;
    }}
    QFrame#line {{ background: {LINE_COLOR}; border: none; }}
    QPushButton#nav {{
        text-align: left;
        padding: 9px 12px;
        border: none;
        border-radius: 8px;
        background: transparent;
        font-size: 13px;
    }}
    QPushButton#nav:hover {{ background: rgba(255,255,255,14); }}
    QPushButton#nav:checked {{
        background: rgba(255,255,255,22);
        border-right: 3px solid {ACCENT};
    }}
    QPushButton#small {{ padding: 4px 10px; }}
    QPushButton#segment {{ padding: 4px 12px; }}
    QPushButton#segment:checked {{
        background: {ACCENT};
        color: white;
        border: 1px solid {ACCENT};
    }}
    QLabel#group {{ color: {TEXT_SUB}; font-size: 12px; font-weight: bold; }}
    QPushButton#remove {{
        background: transparent;
        color: {TEXT_SUB};
        border: none;
        padding: 0px;
    }}
    QPushButton#remove:hover {{ color: {TEXT_WARN}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {TEXT_WARN}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0px; }}
    QScrollBar::handle:vertical {{
        background: rgba(255,255,255,50);
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """
)


def _line() -> QFrame:
    line = QFrame()
    line.setObjectName("line")
    line.setFixedHeight(1)
    return line


def _set_invalid(edit: QLineEdit, invalid: bool):
    """스타일시트의 [invalid="true"] 테두리를 켜고 끈다."""
    if edit.property("invalid") != invalid:
        edit.setProperty("invalid", invalid)
        edit.style().unpolish(edit)
        edit.style().polish(edit)


class _ShortcutEdit(QKeySequenceEdit):
    """키 조합 하나만 받는 입력칸. Esc 는 단축키로 받지 않고 입력을 취소한다."""

    def __init__(self, keys: str, parent=None):
        super().__init__(QKeySequence(keys, QKeySequence.PortableText), parent)
        self.setMaximumSequenceLength(1)
        self.setFixedWidth(KEY_EDIT_WIDTH)
        self._saved = self.keySequence()

    def set_saved(self, keys: str):
        self._saved = QKeySequence(keys, QKeySequence.PortableText)
        self.setKeySequence(self._saved)

    def keys(self) -> str:
        return self.keySequence().toString(QKeySequence.PortableText)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and event.modifiers() == Qt.NoModifier:
            self.setKeySequence(self._saved)
            self.clearFocus()
            return
        super().keyPressEvent(event)


class _SnippetRow(QWidget):
    """`:트리거:` -> 문구 한 줄"""

    changed = Signal()
    removed = Signal(object)  # _SnippetRow

    def __init__(self, trigger: str, text: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.name_edit = QLineEdit(trigger[1:-1] if trigger else "")
        self.name_edit.setPlaceholderText("idea")
        self.name_edit.setFixedWidth(TRIGGER_EDIT_WIDTH)
        self.text_edit = QLineEdit(text)
        self.text_edit.setPlaceholderText("바꿀 문구 (예: 💡)")
        for edit in (self.name_edit, self.text_edit):
            edit.editingFinished.connect(self.changed.emit)

        btn_remove = QPushButton("✕")
        btn_remove.setObjectName("remove")
        btn_remove.setFixedSize(20, 20)
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setToolTip("삭제")
        btn_remove.clicked.connect(lambda: self.removed.emit(self))

        layout.addWidget(QLabel(":"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel(":"))
        arrow = QLabel("→")
        arrow.setObjectName("sub")
        layout.addSpacing(6)
        layout.addWidget(arrow)
        layout.addSpacing(6)
        layout.addWidget(self.text_edit, 1)
        layout.addSpacing(4)
        layout.addWidget(btn_remove)


def _pick_color(initial: str, title: str) -> str:
    """색 선택 창. 취소하면 "".
    설정창 스타일시트(밝은 글자)가 번지지 않도록 부모 없이 띄우고, 설정창(항상 위)보다 위에 둔다."""
    dialog = QColorDialog(QColor(initial))
    dialog.setWindowTitle(title)
    dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    if dialog.exec() != QColorDialog.Accepted:
        return ""
    return dialog.selectedColor().name()


class _ColorButton(QPushButton):
    """색 칩 + 값(#rrggbb / 테마 따름). 누르면 색 선택 창을 띄워 picked 로 알린다."""

    picked = Signal(str)  # "#rrggbb"

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._color = ""
        self.setObjectName("small")
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(COLOR_CHIP_SIZE, COLOR_CHIP_SIZE))
        self.clicked.connect(self._pick)

    def set_color(self, value: str, theme_color: str):
        """value: 고른 색 ("" 이면 테마 따름) / theme_color: 테마 따름일 때 칩에 보일 색"""
        self._color = value or theme_color
        pixmap = QPixmap(COLOR_CHIP_SIZE, COLOR_CHIP_SIZE)
        pixmap.fill(QColor(self._color))
        self.setIcon(QIcon(pixmap))
        self.setText(value or "테마 따름")

    def _pick(self):
        color = _pick_color(self._color, self._title)
        if color:
            self.picked.emit(color)


class SettingsDialog(QWidget):
    shortcuts_changed = Signal(dict)  # {동작: PortableText} - 위젯이 단축키를 다시 건다
    # config 의 "appearance" 가 바뀜 - 위젯이 테마를 다시 입힌다
    appearance_changed = Signal()

    def __init__(self, cfg: dict, version_text: str, parent=None):
        """cfg: 위젯과 같은 설정 dict (여기서 고친 값을 바로 저장한다)"""
        # 항상 위에 둔 위젯(디버그 / 설정) 위에도 보이도록 최상위 힌트를 준다
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self._cfg = cfg
        self._shortcut_edits = {}
        self._shortcut_notes = {}
        self._snippet_rows = []

        self.setObjectName("settings")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(560, 360)
        self.setStyleSheet(SETTINGS_STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 16, 12)
        root.setSpacing(20)
        root.addWidget(self._build_sidebar(version_text))

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_shortcuts_page())
        self.stack.addWidget(self._build_snippets_page())
        self.stack.addWidget(self._build_appearance_page())
        self.stack.addWidget(
            self._build_placeholder_page(
                "Application", "앱 동작 설정이 들어갈 자리입니다."
            )
        )
        root.addWidget(self.stack, 1)

        self._nav_group.button(0).setChecked(True)
        # 단축키 입력칸이 처음부터 키를 가져가지 않도록
        self._nav_group.button(0).setFocus()

    # ==================================================
    # 레이아웃
    # ==================================================
    def _build_sidebar(self, version_text: str) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(4)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for idx, (icon, name) in enumerate(TABS):
            btn = QPushButton()
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(38)
            inner = QHBoxLayout(btn)
            inner.setContentsMargins(12, 0, 12, 0)
            inner.setSpacing(8)
            icon_label = QLabel(icon)
            icon_label.setObjectName("navIcon")
            icon_label.setFixedWidth(NAV_ICON_WIDTH)
            icon_label.setAlignment(Qt.AlignCenter)
            inner.addWidget(icon_label)
            inner.addWidget(QLabel(name), 1)
            for label in (icon_label, inner.itemAt(1).widget()):
                label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._nav_group.addButton(btn, idx)
            layout.addWidget(btn)
        self._nav_group.idClicked.connect(lambda idx: self.stack.setCurrentIndex(idx))

        layout.addStretch(1)
        version = QLabel(version_text)
        version.setObjectName("version")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        return sidebar

    @staticmethod
    def _page(title: str, hint: str = ""):
        """섹션 제목 (+ 보조설명) + 둥근 카드. Returns (페이지, 카드, 카드 레이아웃)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        section = QLabel(title)
        section.setObjectName("section")
        layout.addWidget(section)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("sub")
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)

        card, card_layout = SettingsDialog._card()
        layout.addWidget(card)
        return page, card, card_layout

    @staticmethod
    def _card():
        """둥근 카드. Returns (카드, 카드 레이아웃)"""
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 6, 16, 6)
        card_layout.setSpacing(0)
        return card, card_layout

    @staticmethod
    def _add_row(card_layout: QVBoxLayout, title: str, subtitle: str, *controls):
        """좌측 제목/보조설명 + 우측 컨트롤 한 줄. 보조설명 라벨을 돌려준다."""
        if card_layout.count():
            card_layout.addWidget(_line())
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(8)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(QLabel(title))
        sub = QLabel(subtitle)
        sub.setObjectName("sub")
        texts.addWidget(sub)
        layout.addLayout(texts, 1)
        for control in controls:
            layout.addWidget(control)
        card_layout.addWidget(row)
        return sub

    # ==================================================
    # Keyboard Shortcuts
    # ==================================================
    def _build_shortcuts_page(self) -> QWidget:
        page, _card, card_layout = self._page(
            "Keyboard Shortcuts",
            "위젯을 클릭해 활성화한 상태에서 동작합니다. 입력칸에 커서가 있으면 글자 키는 글자로 입력됩니다.",
        )
        current = widget_config.shortcuts(self._cfg)
        for action, title, subtitle in SHORTCUT_ROWS:
            edit = _ShortcutEdit(current[action])
            edit.editingFinished.connect(
                lambda a=action: self._set_shortcut(a, self._shortcut_edits[a].keys())
            )
            btn_reset = QPushButton("↺")
            btn_reset.setObjectName("small")
            btn_reset.setCursor(Qt.PointingHandCursor)
            btn_reset.setToolTip(
                f"기본값({widget_config.DEFAULT_SHORTCUTS[action]})으로 되돌리기"
            )
            btn_reset.clicked.connect(
                lambda _=False, a=action: self._set_shortcut(
                    a, widget_config.DEFAULT_SHORTCUTS[a]
                )
            )
            self._shortcut_edits[action] = edit
            self._shortcut_notes[action] = (
                self._add_row(card_layout, title, subtitle, edit, btn_reset),
                subtitle,
            )
        page.layout().addStretch(1)
        return page

    def _set_shortcut(self, action: str, keys: str):
        """겹치지 않으면 저장하고 위젯에 알린다. 겹치면 이전 값으로 되돌리고 경고한다."""
        current = widget_config.shortcuts(self._cfg)
        edit = self._shortcut_edits[action]
        clash = next(
            (
                other
                for other, k in current.items()
                if other != action and k and k == keys
            ),
            None,
        )
        if clash is not None:
            edit.set_saved(current[action])
            clash_title = next(t for a, t, _ in SHORTCUT_ROWS if a == clash)
            self._show_shortcut_note(action, f"'{clash_title}'와 겹칩니다", warn=True)
            return
        self._show_shortcut_note(action)
        edit.set_saved(keys)
        if current[action] == keys:
            return
        current[action] = keys
        self._cfg["shortcuts"] = current
        widget_config.save_config(self._cfg)
        self.shortcuts_changed.emit(current)

    def _show_shortcut_note(self, action: str, message: str = "", warn: bool = False):
        label, default_text = self._shortcut_notes[action]
        label.setText(message or default_text)
        label.setStyleSheet(f"color: {TEXT_WARN};" if warn else "")

    # ==================================================
    # Snippets
    # ==================================================
    def _build_snippets_page(self) -> QWidget:
        page, card, card_layout = self._page(
            "Snippets",
            "할 일 · 업무명 입력 중 :idea: 처럼 트리거를 치면 문구로 바뀝니다. 앞뒤 콜론(:)은 자동으로 붙습니다.",
        )
        card_layout.setContentsMargins(16, 12, 10, 12)

        self._snippet_scroll = QScrollArea()
        self._snippet_scroll.setWidgetResizable(True)
        self._snippet_scroll.setFrameShape(QFrame.NoFrame)
        self._snippet_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self._snippet_layout = QVBoxLayout(container)
        self._snippet_layout.setContentsMargins(0, 0, 6, 0)
        self._snippet_layout.setSpacing(6)
        self._snippet_layout.addStretch(1)
        self._snippet_scroll.setWidget(container)
        card_layout.addWidget(self._snippet_scroll)

        for trigger, text in snippets.from_config(self._cfg).items():
            self._append_snippet_row(trigger, text)

        btn_add = QPushButton("+ 추가")
        btn_add.setObjectName("small")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._add_snippet)
        add_row = QHBoxLayout()
        add_row.addWidget(btn_add)
        add_row.addStretch(1)
        page.layout().addLayout(add_row)
        page.layout().setStretchFactor(card, 1)
        return page

    def _append_snippet_row(self, trigger: str, text: str) -> _SnippetRow:
        row = _SnippetRow(trigger, text)
        row.changed.connect(self._save_snippets)
        row.removed.connect(self._remove_snippet)
        # 맨 뒤의 stretch 앞에 넣는다
        self._snippet_layout.insertWidget(self._snippet_layout.count() - 1, row)
        self._snippet_rows.append(row)
        return row

    def _add_snippet(self):
        row = self._append_snippet_row("", "")
        row.name_edit.setFocus()
        self._snippet_scroll.ensureWidgetVisible(row)

    def _remove_snippet(self, row: _SnippetRow):
        self._snippet_rows.remove(row)
        self._snippet_layout.removeWidget(row)
        row.deleteLater()
        self._save_snippets()

    def _save_snippets(self):
        """올바른 행만 저장한다. 빈 칸 / 중복 트리거는 빨간 테두리로 표시만 한다."""
        seen = set()
        saved = []
        for row in self._snippet_rows:
            name = row.name_edit.text().strip()
            text = row.text_edit.text()
            trigger = snippets.normalize_trigger(name)
            blank = not name and not text  # 막 추가한 빈 행은 표시하지 않는다
            name_ok = trigger is not None and trigger not in seen
            _set_invalid(row.name_edit, not blank and not name_ok)
            _set_invalid(row.text_edit, not blank and not text)
            if name_ok and text:
                seen.add(trigger)
                saved.append([trigger, text])
        if saved != self._cfg.get("snippets"):
            self._cfg["snippets"] = saved
            widget_config.save_config(self._cfg)

    # ==================================================
    # Appearance
    # ==================================================
    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        section = QLabel("Appearance")
        section.setObjectName("section")
        hint = QLabel("바꾸는 즉시 위젯에 반영됩니다. 설정창은 다크 테마로 고정됩니다.")
        hint.setObjectName("sub")
        hint.setWordWrap(True)
        layout.addWidget(section)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        groups = QVBoxLayout(container)
        groups.setContentsMargins(0, 0, 6, 0)
        groups.setSpacing(8)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # ---- 위젯 전체 ----
        card_layout = self._add_group(groups, "위젯 전체")
        box, self._theme_group = self._segmented(
            THEME_OPTIONS, lambda v: self._set_appearance("theme", v)
        )
        self._add_row(card_layout, "테마", "시스템은 Windows 앱 모드를 따릅니다", box)
        self._add_row(
            card_layout,
            "강조색",
            "버튼 · 체크박스 · Task 배지 · 선택 표시",
            self._build_swatches(),
        )
        self._bg_button = _ColorButton("배경색")
        self._bg_button.picked.connect(lambda c: self._set_appearance("background", c))
        self._add_row(
            card_layout,
            "배경색",
            "고르면 글자색은 배경 밝기에 맞춰집니다",
            self._bg_button,
            self._reset_button(lambda: self._set_appearance("background", "")),
        )
        self._font_combo = self._build_font_combo()
        self._add_row(card_layout, "폰트", "위젯과 팝업의 글꼴", self._font_combo)

        # ---- 좌패널 ----
        card_layout = self._add_group(groups, "좌패널 (Task)")
        box, self._left_scale_group = self._segmented(
            [(s, SCALE_NAMES[s]) for s in widget_config.LEFT_SCALES],
            lambda v: self._set_appearance("left_scale", v),
        )
        self._add_row(card_layout, "글자 크기", "이름 · 시간 · 버튼 · 투명도", box)

        # ---- 우패널 ----
        card_layout = self._add_group(groups, "우패널 (TODO)")
        box, self._todo_scale_group = self._segmented(
            [(s, SCALE_NAMES[s]) for s in widget_config.TODO_SCALES],
            lambda v: self._set_appearance("todo_scale", v),
        )
        self._add_row(card_layout, "글자 크기", "할 일 목록과 입력칸", box)
        self._todo_color_button = _ColorButton("TODO 글자색")
        self._todo_color_button.picked.connect(
            lambda c: self._set_appearance("todo_text_color", c)
        )
        self._add_row(
            card_layout,
            "글자색",
            "완료한 항목은 흐린 색으로 표시됩니다",
            self._todo_color_button,
            self._reset_button(lambda: self._set_appearance("todo_text_color", "")),
        )
        groups.addStretch(1)

        btn_reset_all = QPushButton("전체 기본값으로")
        btn_reset_all.setObjectName("small")
        btn_reset_all.setCursor(Qt.PointingHandCursor)
        btn_reset_all.clicked.connect(
            lambda: self._save_appearance(dict(widget_config.DEFAULT_APPEARANCE))
        )
        bottom = QHBoxLayout()
        bottom.addWidget(btn_reset_all)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        self._refresh_appearance()
        return page

    def _add_group(self, groups: QVBoxLayout, title: str) -> QVBoxLayout:
        """그룹 제목 + 카드. 카드 레이아웃을 돌려준다."""
        label = QLabel(title)
        label.setObjectName("group")
        card, card_layout = self._card()
        groups.addWidget(label)
        groups.addWidget(card)
        return card_layout

    @staticmethod
    def _segmented(options: list, on_pick):
        """하나만 고르는 버튼 묶음. options: [(값, 표시)]
        Returns (위젯, QButtonGroup) - 버튼 id 는 options 의 index"""
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(box)
        for idx, (_value, label) in enumerate(options):
            btn = QPushButton(label)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            group.addButton(btn, idx)
            layout.addWidget(btn)
        # idClicked 는 사용자가 누를 때만 온다 (setChecked 로 맞출 때는 오지 않음)
        group.idClicked.connect(lambda idx: on_pick(options[idx][0]))
        return box, group

    @staticmethod
    def _reset_button(slot) -> QPushButton:
        btn = QPushButton("↺")
        btn.setObjectName("small")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("테마 색으로 되돌리기")
        btn.clicked.connect(slot)
        return btn

    def _build_swatches(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._swatches = []
        for color, name in ACCENT_SWATCHES:
            btn = self._swatch_button(name)
            btn.clicked.connect(
                lambda _=False, c=color: self._set_appearance("accent", c)
            )
            self._swatches.append((color, btn))
            layout.addWidget(btn)
        self._custom_accent = self._swatch_button("직접 선택")
        self._custom_accent.clicked.connect(self._pick_accent)
        layout.addWidget(self._custom_accent)
        return box

    @staticmethod
    def _swatch_button(tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        return btn

    @staticmethod
    def _paint_swatch(btn: QPushButton, fill: str, ring: str, text: str = ""):
        btn.setText(text)
        btn.setStyleSheet(
            f"QPushButton {{ background: {fill}; color: {TEXT_SUB};"
            f" border: 2px solid {ring}; border-radius: {SWATCH_SIZE // 2}px;"
            " padding: 0px; font-size: 12px; }"
        )

    def _pick_accent(self):
        color = _pick_color(widget_config.appearance(self._cfg)["accent"], "강조색")
        if color:
            self._set_appearance("accent", color)

    def _build_font_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setFixedWidth(FONT_COMBO_WIDTH)
        combo.setMaxVisibleItems(12)
        combo.addItem(DEFAULT_FONT_LABEL, "")
        # 한글을 쓸 수 있는 폰트만. '@' 로 시작하는 것은 세로쓰기용이라 뺀다
        for family in QFontDatabase.families(QFontDatabase.Korean):
            if family.startswith("@"):
                continue
            combo.addItem(family, family)
            preview = QFont(family)
            preview.setPixelSize(13)
            combo.setItemData(combo.count() - 1, preview, Qt.FontRole)
        # activated 는 사용자가 고를 때만 온다
        combo.activated.connect(
            lambda idx: self._set_appearance("font_family", combo.itemData(idx))
        )
        return combo

    def _set_appearance(self, key: str, value):
        current = widget_config.appearance(self._cfg)
        if current[key] != value:
            current[key] = value
            self._save_appearance(current)

    def _save_appearance(self, values: dict):
        self._cfg["appearance"] = values
        widget_config.save_config(self._cfg)
        self.appearance_changed.emit()
        self._refresh_appearance()

    def _refresh_appearance(self):
        """저장된 값으로 Appearance 컨트롤 표시를 맞춘다."""
        a = widget_config.appearance(self._cfg)
        base = theme.build(
            {**a, "background": "", "todo_text_color": ""}, theme.system_dark()
        )  # 테마 따름일 때 칩에 보일 색
        ids = [value for value, _ in THEME_OPTIONS]
        self._theme_group.button(ids.index(a["theme"])).setChecked(True)
        for color, btn in self._swatches:
            self._paint_swatch(btn, color, TEXT_MAIN if color == a["accent"] else color)
        custom = all(color != a["accent"] for color, _ in ACCENT_SWATCHES)
        if custom:
            self._paint_swatch(self._custom_accent, a["accent"], TEXT_MAIN)
        else:
            self._paint_swatch(self._custom_accent, "transparent", TEXT_SUB, "+")
        self._bg_button.set_color(a["background"], base.bg)
        self._todo_color_button.set_color(a["todo_text_color"], base.text_main)
        self._left_scale_group.button(
            widget_config.LEFT_SCALES.index(a["left_scale"])
        ).setChecked(True)
        self._todo_scale_group.button(
            widget_config.TODO_SCALES.index(a["todo_scale"])
        ).setChecked(True)

        idx = self._font_combo.findData(a["font_family"])
        # 저장된 폰트가 지워졌으면 이름만 남겨 둔다 (Qt 가 대체 폰트로 그림)
        if idx < 0:
            self._font_combo.addItem(f"{a['font_family']} (없음)", a["font_family"])
            idx = self._font_combo.count() - 1
        self._font_combo.setCurrentIndex(idx)

    # ==================================================
    # Application (준비 중)
    # ==================================================
    def _build_placeholder_page(self, title: str, subtitle: str) -> QWidget:
        page, _card, card_layout = self._page(title)
        self._add_row(card_layout, "준비 중", subtitle)
        page.layout().addStretch(1)
        return page

    # ==================================================
    # 표시
    # ==================================================
    def show_front(self):
        """띄우고(이미 떠 있으면 그대로) 앞으로 올린다."""
        self.showNormal()
        os_win.set_dark_title_bar(int(self.winId()))
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

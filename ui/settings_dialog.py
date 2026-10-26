"""설정창 (위젯 우클릭 "설정" / 설정 단축키 Ctrl+,)

좌측 사이드바에서 탭을 고르고 우측 카드에서 바로 바꾼다 (확인 버튼 없이 즉시 config.json 에 저장).
  - Keyboard Shortcuts : 위젯 단축키. 다른 동작과 겹치면 저장하지 않고 경고
  - Snippets           : `:트리거:` -> 문구 목록. 빈 칸 / 중복 트리거는 저장하지 않고 표시만
  - Appearance         : 테마 / 강조색 / 배경색 / 글자도 함께 투명 / 폰트, 좌·우패널 글자 크기, TODO 글자색,
                         리마인더 알림 창 폭 / 글자 크기(실제 크기 예시 포함),
                         사용자 태그(이름 / 색 변경, 추가, 삭제 - config.json custom_tags).
                         바꾸면 appearance_changed 로 위젯에 바로 반영한다.
  - Application        : 설정 내보내기(폴더를 고르면 config.json 을 그대로 저장) / 가져오기(바로 적용)

설정창 자체는 테마(다크 / 라이트)와 강조색만 따른다. 배경색 / 폰트 / 글자 크기는 위젯에만 적용한다.

키보드
  - Esc : 닫기 (단축키 입력칸에서는 입력 취소)
"""

import os
from datetime import datetime

from PySide6.QtCore import QSize, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
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
from ui.color_dialog import pick_color
from ui.confirm_dialog import ConfirmDialog
from ui.reminder_popup import ReminderPopup
from ui.tag_dialog import TagDialog


WINDOW_TITLE = "Task알림 설정"
WINDOW_SIZE = (720, 560)  # Appearance 탭이 스크롤 없이 거의 다 보이도록
# 테마별 (창 배경, 카드 배경) - 카드가 창보다 한 단계 떠 보이도록
SURFACES = {True: ("#18181a", "#232326"), False: ("#ececef", "#ffffff")}
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
    ("task_register", "Task 등록/해제", "Task가 없으면 등록, 진행 중이면 해제합니다"),
    ("task_edit", "Task 수정", "진행 중인 Task를 수정합니다"),
    ("task_clear", "Task 완료", "진행 중인 Task를 완료합니다"),
    ("todo_focus", "할 일 추가", "할 일 입력칸으로 커서 이동"),
    ("todo_search", "할 일 검색", "검색 · 날짜별 보기 줄을 엽니다"),
    ("settings", "설정 열기", "이 설정창을 엽니다"),
]

# Appearance 선택지 (값, 표시) - 값은 widget_config.THEMES / LEFT_SCALES / TODO_SCALES 와 같다
THEME_OPTIONS = [("dark", "다크"), ("light", "라이트"), ("system", "시스템")]
ON_OFF_OPTIONS = [(False, "끔"), (True, "켬")]
SCALE_NAMES = {90: "작게", 100: "보통", 115: "크게", 130: "아주 크게"}
POPUP_WIDTH_NAMES = {220: "좁게", 260: "보통", 320: "넓게", 380: "아주 넓게"}
POPUP_PREVIEW_TEXT = "회의자료 준비하기 (예시)"
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
EXPORT_HINT = "폴더를 고르면 지금 설정을 JSON 파일로 그대로 저장합니다"
IMPORT_HINT = "내보낸 JSON 파일로 지금 설정을 바꾸고 바로 적용합니다"


def _settings_theme(cfg: dict) -> theme.Theme:
    """설정창의 테마: 다크 / 라이트와 강조색만 위젯 설정을 따른다."""
    a = widget_config.appearance(cfg)
    return theme.build(
        {**a, "background": "", "font_family": "", "todo_text_color": ""},
        theme.system_dark(),
    )


def _settings_style(t: theme.Theme) -> str:
    window_bg, card_bg = SURFACES[t.dark]
    return (
        theme.button_style(t)
        + theme.popup_form_style(t)
        + theme.menu_style(t)  # 입력칸 우클릭 메뉴
        + f"""
    QWidget#settings {{ background: {window_bg}; }}
    QLabel {{
        background: transparent;
        color: {t.text_main};
        font-family: {t.font_family};
        font-size: 13px;
    }}
    QLabel#sub {{ color: {t.text_sub}; font-size: 11px; }}
    QLabel#section {{ font-size: 14px; font-weight: bold; }}
    QLabel#navIcon {{ font-size: 15px; color: {t.text_sub}; }}
    QLabel#version {{
        color: {t.text_sub};
        font-weight: bold;
        border: 1px solid {t.overlay(40)};
        border-radius: 14px;
        padding: 6px;
    }}
    QFrame#card, QFrame#sidebar {{
        background: {card_bg};
        border: 1px solid {t.overlay(22)};
        border-radius: 14px;
    }}
    QFrame#line {{ background: {t.line}; border: none; }}
    QPushButton#nav {{
        text-align: left;
        padding: 9px 12px;
        border: none;
        border-radius: 8px;
        background: transparent;
        font-size: 13px;
    }}
    QPushButton#nav:hover {{ background: {t.overlay(14)}; }}
    QPushButton#nav:checked {{
        background: {t.overlay(22)};
        border-right: 3px solid {t.accent};
    }}
    QPushButton#small {{ padding: 4px 10px; }}
    QPushButton#segment {{ padding: 4px 12px; }}
    QPushButton#segment:checked {{
        background: {t.accent};
        color: {t.on_accent};
        border: 1px solid {t.accent};
    }}
    QLabel#group {{ color: {t.text_sub}; font-size: 12px; font-weight: bold; }}
    QPushButton#remove {{
        background: transparent;
        color: {t.text_sub};
        border: none;
        padding: 0px;
    }}
    QPushButton#remove:hover {{ color: {t.text_warn}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {t.text_warn}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
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
        color = pick_color(self._color, self._title)
        if color:
            self.picked.emit(color)


class _TagRow(QWidget):
    """사용자 태그 한 줄: [색] 이름 [✕]"""

    changed = Signal(object)  # _TagRow - 이름 / 색을 바꿈
    removed = Signal(object)  # _TagRow

    def __init__(self, tag: dict, parent=None):
        super().__init__(parent)
        self.tag_id = tag["id"]
        self.color = tag["color"]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.color_button = _ColorButton("태그 색")
        self.color_button.set_color(self.color, "")
        self.color_button.picked.connect(self._on_color)
        self.name_edit = QLineEdit(tag["name"])
        self.name_edit.setMaxLength(widget_config.CUSTOM_TAG_NAME_MAX)
        self.name_edit.setPlaceholderText("이름")
        self.name_edit.editingFinished.connect(lambda: self.changed.emit(self))

        btn_remove = QPushButton("✕")
        btn_remove.setObjectName("remove")
        btn_remove.setFixedSize(20, 20)
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setToolTip("삭제 (이 태그를 붙인 할 일은 태그 없음으로 보입니다)")
        btn_remove.clicked.connect(lambda: self.removed.emit(self))

        layout.addWidget(self.color_button)
        layout.addWidget(self.name_edit, 1)
        layout.addWidget(btn_remove)

    def _on_color(self, color: str):
        self.color = color
        self.color_button.set_color(color, "")
        self.changed.emit(self)

    def name(self) -> str:
        return self.name_edit.text().strip()


class SettingsDialog(QWidget):
    shortcuts_changed = Signal(dict)  # {동작: PortableText} - 위젯이 단축키를 다시 건다
    # config 의 "appearance" 가 바뀜 - 위젯이 테마를 다시 입힌다
    appearance_changed = Signal()
    # 설정 가져오기 - 새 설정 dict. TaskPinApp 이 cfg 를 바꾸고 위젯 / 이 창에 다시 적용한다
    config_imported = Signal(dict)

    def __init__(self, cfg: dict, version_text: str, parent=None):
        """cfg: 위젯과 같은 설정 dict (여기서 고친 값을 바로 저장한다)"""
        # 항상 위에 둔 위젯(디버그 / 설정) 위에도 보이도록 최상위 힌트를 준다
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self._cfg = cfg
        self._look = _settings_theme(cfg)  # 설정창 자신의 테마 (apply_theme)
        self._shortcut_edits = {}
        self._shortcut_notes = {}
        self._snippet_rows = []

        self.setObjectName("settings")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(560, 360)
        self.setStyleSheet(_settings_style(self._look))

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 16, 12)
        root.setSpacing(20)
        root.addWidget(self._build_sidebar(version_text))

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_shortcuts_page())
        self.stack.addWidget(self._build_snippets_page())
        self.stack.addWidget(self._build_appearance_page())
        self.stack.addWidget(self._build_application_page())
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
        label.setStyleSheet(f"color: {self._look.text_warn};" if warn else "")

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
        hint = QLabel(
            "바꾸는 즉시 위젯에 반영됩니다. 설정창은 테마(다크 / 라이트)와 강조색만 따릅니다."
        )
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
        box, self._fade_text_group = self._segmented(
            ON_OFF_OPTIONS, lambda v: self._set_appearance("fade_text", v)
        )
        self._add_row(
            card_layout,
            "글자도 함께 투명",
            "켜면 투명도 슬라이더가 글자까지 투명하게 합니다 (끄면 배경만)",
            box,
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

        # ---- 리마인더 알림 창 ----
        card_layout = self._add_group(groups, "알림 창 (리마인더)")
        box, self._popup_width_group = self._segmented(
            [(w, POPUP_WIDTH_NAMES[w]) for w in widget_config.POPUP_WIDTHS],
            lambda v: self._set_appearance("popup_width", v),
        )
        self._popup_width_sub = self._add_row(card_layout, "크기", "", box)
        box, self._popup_scale_group = self._segmented(
            [(s, SCALE_NAMES[s]) for s in widget_config.POPUP_SCALES],
            lambda v: self._set_appearance("popup_scale", v),
        )
        self._add_row(card_layout, "글자 크기", "제목 · 내용 · 버튼", box)
        # 실제 알림 창과 같은 크기 / 테마로 그린 예시 (값을 바꿀 때마다 다시 만든다)
        card_layout.addWidget(_line())
        preview_row = QWidget()
        self._popup_preview_layout = QVBoxLayout(preview_row)
        self._popup_preview_layout.setContentsMargins(0, 10, 0, 12)
        self._popup_preview_layout.setSpacing(8)
        preview_sub = QLabel("실제 크기 예시 · 높이는 내용에 맞춰집니다")
        preview_sub.setObjectName("sub")
        self._popup_preview_layout.addWidget(preview_sub)
        self._popup_preview = None
        card_layout.addWidget(preview_row)

        # ---- 사용자 태그 (우패널 우클릭 "태그" 의 "태그 없음" 아래에 보인다) ----
        card_layout = self._add_group(groups, "TODO 태그")
        tags_box = QWidget()
        self._tag_layout = QVBoxLayout(tags_box)
        self._tag_layout.setContentsMargins(0, 10, 0, 10)
        self._tag_layout.setSpacing(6)
        self._tag_empty = QLabel(
            "추가한 태그가 없습니다. 할 일 우클릭 → 태그 → '+ 태그 추가…'로도 추가할 수 있습니다."
        )
        self._tag_empty.setObjectName("sub")
        self._tag_empty.setWordWrap(True)
        self._tag_layout.addWidget(self._tag_empty)
        btn_add_tag = QPushButton("+ 태그 추가")
        btn_add_tag.setObjectName("small")
        btn_add_tag.setCursor(Qt.PointingHandCursor)
        btn_add_tag.clicked.connect(self._add_tag)
        add_row = QHBoxLayout()
        add_row.addWidget(btn_add_tag)
        add_row.addStretch(1)
        self._tag_layout.addLayout(add_row)
        card_layout.addWidget(tags_box)
        self._tag_rows = []
        self._rebuild_tag_rows()
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

    # ---- 사용자 태그 ----
    def _rebuild_tag_rows(self):
        for row in self._tag_rows:
            self._tag_layout.removeWidget(row)
            row.deleteLater()
        self._tag_rows = []
        tags = widget_config.custom_tags(self._cfg)
        for idx, tag in enumerate(tags):
            row = _TagRow(tag)
            row.changed.connect(self._on_tag_changed)
            row.removed.connect(self._remove_tag)
            # 빈 안내 라벨 다음, "+ 태그 추가" 줄 앞
            self._tag_layout.insertWidget(1 + idx, row)
            self._tag_rows.append(row)
        self._tag_empty.setVisible(not tags)

    def _save_tags(self, tags: list):
        """위젯 쪽("+ 태그 추가…")에서 그사이 추가한 태그를 지우지 않도록 cfg 의 목록을 고쳐서 넘긴다."""
        self._cfg["custom_tags"] = widget_config.custom_tags({"custom_tags": tags})
        widget_config.save_config(self._cfg)
        self.appearance_changed.emit()  # 위젯이 태그 막대를 다시 그린다

    def _on_tag_changed(self, row: _TagRow):
        tags = widget_config.custom_tags(self._cfg)
        for tag in tags:
            if tag["id"] == row.tag_id:
                tag["name"], tag["color"] = row.name() or row.color, row.color
        if not row.name():
            row.name_edit.setText(row.color)  # 이름을 비우면 색 코드로
        self._save_tags(tags)

    def _remove_tag(self, row: _TagRow):
        self._save_tags(
            [t for t in widget_config.custom_tags(self._cfg) if t["id"] != row.tag_id]
        )
        self._rebuild_tag_rows()

    def _add_tag(self):
        dialog = TagDialog(parent=self)
        if dialog.exec_over(self):
            widget_config.add_custom_tag(self._cfg, dialog.name(), dialog.color())
            self._save_tags(self._cfg["custom_tags"])
            self._rebuild_tag_rows()

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

    def _paint_swatch(self, btn: QPushButton, fill: str, ring: str, text: str = ""):
        btn.setText(text)
        btn.setStyleSheet(
            f"QPushButton {{ background: {fill}; color: {self._look.text_sub};"
            f" border: 2px solid {ring}; border-radius: {SWATCH_SIZE // 2}px;"
            " padding: 0px; font-size: 12px; }"
        )

    def _pick_accent(self):
        color = pick_color(widget_config.appearance(self._cfg)["accent"], "강조색")
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
        self.apply_theme()

    def apply_theme(self):
        """설정창에도 테마(다크 / 라이트, 강조색)를 다시 입히고 Appearance 표시를 맞춘다.
        "시스템" 테마에서 Windows 앱 모드가 바뀔 때 TaskPinApp 도 부른다."""
        self._look = _settings_theme(self._cfg)
        self.setStyleSheet(_settings_style(self._look))
        if self.isVisible():
            os_win.set_dark_title_bar(int(self.winId()), self._look.dark)
        self._refresh_appearance()

    def _refresh_appearance(self):
        """저장된 값으로 Appearance 컨트롤 표시를 맞춘다."""
        a = widget_config.appearance(self._cfg)
        look = self._look  # 배경색 / 글자색을 고르지 않았을 때(테마 따름) 칩에 보일 색
        ids = [value for value, _ in THEME_OPTIONS]
        self._theme_group.button(ids.index(a["theme"])).setChecked(True)
        for color, btn in self._swatches:
            ring = look.text_main if color == a["accent"] else color
            self._paint_swatch(btn, color, ring)
        custom = all(color != a["accent"] for color, _ in ACCENT_SWATCHES)
        if custom:
            self._paint_swatch(self._custom_accent, a["accent"], look.text_main)
        else:
            self._paint_swatch(self._custom_accent, "transparent", look.text_sub, "+")
        self._bg_button.set_color(a["background"], look.bg)
        self._fade_text_group.button(int(a["fade_text"])).setChecked(True)
        self._todo_color_button.set_color(a["todo_text_color"], look.text_main)
        self._left_scale_group.button(
            widget_config.LEFT_SCALES.index(a["left_scale"])
        ).setChecked(True)
        self._todo_scale_group.button(
            widget_config.TODO_SCALES.index(a["todo_scale"])
        ).setChecked(True)
        self._popup_width_group.button(
            widget_config.POPUP_WIDTHS.index(a["popup_width"])
        ).setChecked(True)
        self._popup_scale_group.button(
            widget_config.POPUP_SCALES.index(a["popup_scale"])
        ).setChecked(True)
        self._popup_width_sub.setText(f"폭 {a['popup_width']}px")
        self._rebuild_popup_preview(a)

        idx = self._font_combo.findData(a["font_family"])
        # 저장된 폰트가 지워졌으면 이름만 남겨 둔다 (Qt 가 대체 폰트로 그림)
        if idx < 0:
            self._font_combo.addItem(f"{a['font_family']} (없음)", a["font_family"])
            idx = self._font_combo.count() - 1
        self._font_combo.setCurrentIndex(idx)

    def _rebuild_popup_preview(self, a: dict):
        """알림 창 예시를 지금 설정으로 다시 만든다. 설정창 테마가 아니라 실제 팝업과 같은
        위젯 테마(배경색 / 폰트 포함)로, 같은 폭 / 글자 크기로 그린다."""
        if self._popup_preview is not None:
            self._popup_preview_layout.removeWidget(self._popup_preview)
            self._popup_preview.deleteLater()
        due = datetime.now().astimezone().replace(second=0, microsecond=0)
        self._popup_preview = ReminderPopup(
            "",
            POPUP_PREVIEW_TEXT,
            due,
            look=theme.build(a, theme.system_dark()),
            preview=True,
        )
        self._popup_preview_layout.addWidget(self._popup_preview, 0, Qt.AlignLeft)

    # ==================================================
    # Application: 설정 내보내기 / 가져오기
    # ==================================================
    def _build_application_page(self) -> QWidget:
        page, _card, card_layout = self._page(
            "Application",
            "위젯 설정(config.json)을 파일로 내보내거나 가져옵니다. TODO / Task 기록은 들어가지 않습니다.",
        )
        btn_export = QPushButton("내보내기…")
        btn_export.clicked.connect(self._export_config)
        btn_import = QPushButton("가져오기…")
        btn_import.clicked.connect(self._import_config)
        for btn in (btn_export, btn_import):
            btn.setObjectName("small")
            btn.setCursor(Qt.PointingHandCursor)
        self._export_note = self._add_row(
            card_layout,
            "설정 내보내기",
            EXPORT_HINT,
            btn_export,
        )
        self._import_note = self._add_row(
            card_layout,
            "설정 가져오기",
            IMPORT_HINT,
            btn_import,
        )
        for note in (self._export_note, self._import_note):
            note.setWordWrap(True)
        page.layout().addStretch(1)
        return page

    def _start_folder(self) -> str:
        return self._cfg.get("export_dir") or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation
        )

    def _show_note(self, label: QLabel, message: str, warn: bool = False):
        label.setText(message)
        label.setStyleSheet(f"color: {self._look.text_warn};" if warn else "")

    def _export_config(self):
        folder = QFileDialog.getExistingDirectory(
            self, "설정을 내보낼 폴더", self._start_folder()
        )
        if not folder:
            return
        try:
            path = widget_config.export_config(self._cfg, folder, datetime.now())
        except OSError as e:
            self._show_note(self._export_note, f"저장하지 못했습니다. {e}", warn=True)
            return
        self._show_note(self._export_note, f"저장했습니다: {os.path.normpath(path)}")
        self._cfg["export_dir"] = folder
        widget_config.save_config(self._cfg)

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "설정 가져오기", self._start_folder(), "JSON (*.json)"
        )
        if not path:
            return
        new = widget_config.read_import(path)
        if new is None:
            self._show_note(
                self._import_note,
                "Task알림 설정 파일이 아니거나 읽지 못했습니다.",
                warn=True,
            )
            return
        dialog = ConfirmDialog(
            "설정 가져오기",
            "지금 설정을 이 파일의 설정으로 바꿀까요?",
            confirm_text="가져오기",
            note=os.path.basename(path),
            parent=self,
        )
        if not dialog.exec_over(self):
            return
        self.config_imported.emit(new)
        self._show_note(self._import_note, f"가져왔습니다: {os.path.basename(path)}")

    def reload_values(self):
        """설정 가져오기 뒤: 모든 탭의 표시를 바뀐 cfg 로 다시 맞춘다."""
        current = widget_config.shortcuts(self._cfg)
        for action, edit in self._shortcut_edits.items():
            edit.set_saved(current[action])
            self._show_shortcut_note(action)
        for row in list(self._snippet_rows):
            self._snippet_layout.removeWidget(row)
            row.deleteLater()
        self._snippet_rows = []
        for trigger, text in snippets.from_config(self._cfg).items():
            self._append_snippet_row(trigger, text)
        self._rebuild_tag_rows()
        self.apply_theme()

    # ==================================================
    # 표시
    # ==================================================
    def show_front(self):
        """띄우고(이미 떠 있으면 그대로) 앞으로 올린다."""
        self._rebuild_tag_rows()  # 닫혀 있는 동안 위젯 태그 메뉴에서 추가했을 수 있다
        self.showNormal()
        os_win.set_dark_title_bar(int(self.winId()), self._look.dark)
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

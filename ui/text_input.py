"""입력칸 공통 보조: Win+. 이모지 패널 입력 보정, 스니펫 치환"""

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer, Signal
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from manager import os_win, snippets


class ImeCharFilter(QAbstractNativeEventFilter):
    """이모지 패널이 보낸 문자를 Qt 대신 받아, 포커스된 입력칸에 IME 확정 문자열로 넣는다.
    (Qt 6.8 은 WM_IME_CHAR 의 서로게이트 쌍을 버려서 🚀 같은 이모지가 들어가지 않는다)

    한글 조합은 WM_IME_COMPOSITION 으로 Qt 가 처리하므로 여기를 지나지 않는다.
    QApplication.installNativeEventFilter 로 앱 전체(위젯 / 등록 창 / 설정창)에 건다."""

    def __init__(self):
        super().__init__()
        self._decoder = os_win.ImeCharDecoder()

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        decoded = os_win.char_message(int(message))
        if decoded is None:
            return False, 0
        swallow, text = self._decoder.feed(*decoded)
        if text:
            _commit_text(text)
        return swallow, 0


def _commit_text(text: str):
    target = QApplication.focusWidget()
    if target is None or not target.testAttribute(Qt.WA_InputMethodEnabled):
        return
    event = QInputMethodEvent()
    event.setCommitString(text)
    QApplication.sendEvent(target, event)


def py_cursor(edit: QLineEdit) -> int:
    """커서 위치를 파이썬 문자열 index 로.
    QLineEdit 위치는 UTF-16 단위라 앞에 🚀 같은 이모지(서로게이트 쌍)가 있으면 어긋난다."""
    units = edit.text().encode("utf-16-le")[: edit.cursorPosition() * 2]
    return len(units.decode("utf-16-le", "ignore"))


def utf16_pos(text: str, index: int) -> int:
    """파이썬 문자열 index -> QLineEdit 위치(UTF-16 단위)"""
    return len(text[:index].encode("utf-16-le")) // 2


class PreeditLineEdit(QLineEdit):
    """조합 중인 한글(preedit)을 기억하는 입력칸. full_text() 는 조합 중인 글자까지 합쳐 읽는다.
    (조합 중인 마지막 글자는 확정되기 전까지 text() 에 빠진다)"""

    preedit_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preedit = ""

    def inputMethodEvent(self, event):
        self.preedit = event.preeditString()
        super().inputMethodEvent(event)
        self.preedit_changed.emit()

    def full_text(self) -> str:
        text = self.text()
        if self.preedit:
            pos = py_cursor(self)
            text = text[:pos] + self.preedit + text[pos:]
        return text


def expand_snippet_later(edit: QLineEdit, snippets_provider):
    """textEdited 에서 부른다. 커서 바로 앞의 `:트리거:` 를 문구로 바꾼다.

    textEdited 안에서 바로 고치면 되돌리기 기록이 꼬여 Ctrl+Z 가 듣지 않으므로 다음 차례에 바꾼다.
    setText 는 되돌리기 기록을 지우므로 선택 + insert 로 바꾼다 (Ctrl+Z 로 원래 글자 복원)
    snippets_provider: () -> {트리거: 문구}"""

    def expand():
        text = edit.text()
        hit = snippets.expand(text, py_cursor(edit), snippets_provider())
        if hit is not None:
            start, end, replacement = hit
            begin = utf16_pos(text, start)
            edit.setSelection(begin, utf16_pos(text, end) - begin)
            edit.insert(replacement)

    QTimer.singleShot(0, edit, expand)

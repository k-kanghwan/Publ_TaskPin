"""스크롤 영역의 세로 휠을 미끄러지게 (페이지 칩 줄 page_bar.PageTabs 와 같은 느낌)

마우스 휠 한 칸은 Qt 기본과 같은 거리(윈도우 "한 번에 스크롤할 줄 수" x singleStep)를 SCROLL_ANIM_MS 동안
OutCubic 으로 옮긴다. 미끄러지는 중에 더 굴리면 지금 목표에서 더 밀어 끊기지 않고 쌓인다.
터치패드(pixelDelta)는 이미 조금씩 매끄럽게 오므로 바로 따라가고, Ctrl / Shift 휠과 가로 휠은 Qt 기본이다.
다른 곳에서 값을 바꾸면(스크롤바 끌기 / 트랙 클릭 / ensureWidgetVisible / 드래그 자동 스크롤) 멈춘다.
"""

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Qt, QVariantAnimation
from PySide6.QtWidgets import QAbstractScrollArea, QApplication

SCROLL_ANIM_MS = 220  # 미끄러지는 시간 (TODO 목록 휠 / 페이지 칩 줄 휠·트랙 클릭·페이지 넘김)


class SmoothScroll(QObject):
    def __init__(self, area: QAbstractScrollArea):
        super().__init__(area)
        self._bar = area.verticalScrollBar()
        self._target = 0
        self._setting = False  # 애니메이션이 값을 바꾸는 중 (다른 곳의 변경과 구별)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(SCROLL_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._apply)
        self._bar.valueChanged.connect(self._on_value_changed)
        self._bar.rangeChanged.connect(self._on_range_changed)
        area.viewport().installEventFilter(self)
        self._bar.installEventFilter(self)  # 스크롤바 위에서 굴려도 같게

    # ---- 밖에서 부르는 것 ----
    def scrolling(self) -> bool:
        return self._anim.state() == QVariantAnimation.Running

    def value(self) -> int:
        """지금 자리 - 미끄러지는 중이면 가려던 자리 (페이지 스크롤 기억에 남길 값)"""
        return self._target if self.scrolling() else self._bar.value()

    def stop(self):
        """남은 미끄러짐을 멈춘다 - 값을 바로 정하는 곳(행 보이기 / 페이지 넘김)이 먼저 부른다.
        값이 그대로면 valueChanged 가 오지 않아 저절로 멈추지 않는다."""
        self._anim.stop()

    def scroll_by(self, dy: float) -> bool:
        """dy 만큼 미끄러진다 (미끄러지는 중이면 그 목표에서 더). 움직일 곳이 있으면 True"""
        base = self._target if self.scrolling() else self._bar.value()
        target = self._clamp(base + dy)
        if target == base:
            return False
        self._slide_to(target)
        return True

    # ---- 안쪽 ----
    def _clamp(self, value: float) -> int:
        return int(round(min(max(self._bar.minimum(), value), self._bar.maximum())))

    def _slide_to(self, target: int):
        self._anim.stop()
        self._target = target
        if target == self._bar.value():
            return
        self._anim.setStartValue(float(self._bar.value()))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def _apply(self, value):
        self._setting = True
        try:
            self._bar.setValue(int(round(value)))
        finally:
            self._setting = False

    def _on_value_changed(self, _value):
        if not self._setting and self.scrolling():
            self._anim.stop()  # 스크롤바 끌기 / 행 보이기 등이 값을 정했다

    def _on_range_changed(self, _low, _high):
        # 미끄러지는 중에 목록 높이가 바뀌면(행 추가 / 접기) 목표를 범위 안으로
        if self.scrolling():
            target = self._clamp(self._target)
            if target != self._target:
                self._slide_to(target)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Wheel:
            return False
        if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier):
            return False  # Qt 기본 (페이지 단위 / 가로)
        amount = event.angleDelta().y()
        if not amount:
            return False  # 가로 휠
        pixel = event.pixelDelta()
        if not pixel.isNull():  # 터치패드: 이미 매끄럽게 조금씩 온다 - 바로 따라간다
            self._anim.stop()
            self._bar.setValue(self._bar.value() - pixel.y())
            return True
        step = QApplication.wheelScrollLines() * self._bar.singleStep()
        self.scroll_by(-amount / 120 * step)
        return True  # 끝이라 못 움직여도 휠은 여기서 끝 (위젯으로 올려 보내지 않음)

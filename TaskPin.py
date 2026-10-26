"""Task알림 (TaskPin) - 업무(Task) 시간 관리 + TODO 리마인더 바탕화면 위젯"""

# ---- Nuitka 빌드 옵션 (python -m nuitka TaskPin.py -> build/TaskPin.dist) ----
# 배포는 이 standalone 폴더를 Inno Setup(installer/TaskPin.iss)으로 묶은 설치본만 쓴다.
# 버전을 올릴 때는 version.py 만 고친다. (--product-version 도 거기서 읽고, 설치본은 exe 에서 읽음)
# nuitka-project-set: APP_VERSION = __import__("re").search(r'^VERSION = "(.+)"', open({MAIN_DIRECTORY} + "/version.py", encoding="utf-8").read(), __import__("re").M).group(1)
# nuitka-project: --mode=standalone
# nuitka-project: --output-dir={MAIN_DIRECTORY}/build
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/ico/taskpin.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/ico/taskpin_icon_A_memo.svg=ico/taskpin_icon_A_memo.svg
# nuitka-project: --product-name=Task알림
# nuitka-project: --product-version={APP_VERSION}
# nuitka-project: --file-description=Task알림
# nuitka-project: --output-filename=Task알림.exe
# nuitka-project: --assume-yes-for-downloads

# fmt: off
# ========= ========= ========= ========= =========

APP_NAME = "Task알림"

# ========= ========= ========= ========= =========
# fmt: on

import getpass
import os
import sys
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from manager import db, os_win, snippets, task_clock, task_store, widget_config
from ui import theme
from ui.clock_widget import ClockWidget
from ui.confirm_dialog import ConfirmDialog
from ui.settings_dialog import SettingsDialog
from ui.task_picker import TaskPicker
from ui.text_input import ImeCharFilter
from ui.tray_app import TrayApp
from version import VERSION

# VS Code 디버그 실행(.vscode/launch.json): 위젯 항상 위, 실제 앱과 분리
# (데이터는 launch.json 이 APPDATA 를 .debug_appdata 로 바꿔 분리한다)
DEBUG = os.environ.get("TASKPIN_DEBUG") == "1"


class TaskPinApp(TrayApp):
    # 단일 인스턴스 ID - 디버그는 설치본이 실행 중이어도 같이 뜨도록 분리
    APP_ID = f"{getpass.getuser()}_TaskPin" + ("_debug" if DEBUG else "")

    def __init__(self):
        super().__init__()
        self.tray.setToolTip(f"{APP_NAME} {VERSION}" + (" (debug)" if DEBUG else ""))

        # ==========================
        # Task 시간 (가장 최근 등록 1건)
        self._task = task_store.latest()
        self._shown_task = None  # 위젯에 마지막으로 반영한 Task
        # 종료 알림을 보낸 Task id - 켤 때 이미 끝난 Task 는 알린 것으로 친다
        self._notified_task_ids = set()
        if self._task is not None and self._task.end_at <= datetime.now().astimezone():
            self._notified_task_ids.add(self._task.id)

        # ==========================
        # 바탕화면 위젯
        self.widget_cfg = widget_config.load_config()
        # 등록된 명령이 낡았으면 갱신 (디버그에서는 설치본 exe 등록값을 python 명령으로 덮어쓰지 않도록 건너뜀)
        if not DEBUG:
            os_win.sync_autostart_command()
        # 테마는 위젯을 만들기 전에 건다 (위젯 / 팝업은 만들 때 theme.current() 를 읽는다)
        self._base_font = QApplication.font()
        self._apply_theme()
        self.widget = ClockWidget(self.widget_cfg, force_on_top=DEBUG)
        self._settings = None  # 열려 있는 설정창 (한 번에 하나)

        self.widget.task_register_requested.connect(self.open_task_picker)
        self.widget.task_clear_requested.connect(self.clear_task)
        self.widget.settings_requested.connect(self.open_settings)
        self.widget.quit_requested.connect(self.app_close)
        self.widget.visibility_changed.connect(self.sync_widget_toggle_action)
        self.widget.reminder_due.connect(
            lambda _id, text: self.send_message_info("⏰ 리마인더", text)
        )
        # "시스템" 테마: Windows 앱 모드가 바뀌면 따라간다
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed
        )

        widget_visible = bool(self.widget_cfg.get("visible", True))
        if widget_visible:
            self.widget.show()

        # setChecked 가 toggled 를 발생시키므로 연결 전에 상태를 맞춘다
        self.action_toggle_widget.setChecked(widget_visible)
        self.action_toggle_widget.toggled.connect(self.toggle_widget)

        # 트레이 아이콘 좌클릭: 위젯을 다른 앱보다 위로 (다른 앱을 쓰면 다시 바탕화면으로)
        self.tray.activated.connect(self.on_tray_activated)

        # 위젯 시계/카운트다운
        self.widget_tick = QTimer()
        self.widget_tick.timeout.connect(self.tick_widget)
        self.widget_tick.start(1000)
        self.tick_widget()

    # ==========================
    # 바탕화면 위젯 연동
    # ==========================
    def tick_widget(self):
        """1초마다 Task 종료 알림 확인 + 위젯의 현재시간과 남은시간을 갱신"""
        now = datetime.now().astimezone()
        task = self._task if task_store.is_current(self._task, now) else None

        # 종료 알림은 위젯이 숨겨져 있어도 보낸다
        if (
            task is not None
            and task.end_at <= now
            and task.id not in self._notified_task_ids
        ):
            self._notified_task_ids.add(task.id)
            self.send_message_info(
                "Task 종료", task.title or "등록한 Task 시간이 끝났습니다"
            )

        # 날짜가 바뀌어 지난 Task 가 빠지는 경우도 여기서 반영된다
        if task != self._shown_task:
            self._shown_task = task
            self.widget.apply_task(task)

        if self.widget.isVisible():
            end = task.end_at if task is not None else None
            self.widget.set_clock(
                now.strftime("%H:%M:%S"), task_clock.remaining_display(end, now)
            )

    def open_task_picker(self):
        """위젯의 'Task 등록' 버튼: 등록 창을 버튼 위에 띄운다."""
        picker = TaskPicker(
            self._shown_task, lambda: snippets.from_config(self.widget_cfg), self.widget
        )
        picker.picked.connect(self.register_task)
        picker.popup_for(self.widget.btn_task)

    def register_task(
        self, title: str, detail: str, start_at: datetime, end_at: datetime
    ):
        task = task_store.register(title, detail, start_at, end_at)
        if task is None:
            self.tray.showMessage(
                "Task 등록", "저장하지 못했습니다.", QSystemTrayIcon.Warning
            )
            return
        if task.end_at <= datetime.now().astimezone():
            self._notified_task_ids.add(
                task.id
            )  # 이미 끝난 시간으로 등록하면 알리지 않는다
        self._task = task
        self.tick_widget()

    def clear_task(self):
        """위젯의 'Task 완료' 버튼: 확인 후 기록은 남기고 위젯에서 내린다 (종료 알림도 보내지 않음)"""
        task = self._shown_task
        if task is None or not self._confirm_clear(task):
            return
        if not task_store.clear(task.id):
            self.tray.showMessage(
                "Task 해제", "저장하지 못했습니다.", QSystemTrayIcon.Warning
            )
            return
        self._task = None
        self.tick_widget()

    def _confirm_clear(self, task) -> bool:
        """종료까지 시간이 남았으면 남은시간을 보여주고, 아니면 해제 여부만 묻는다."""
        now = datetime.now().astimezone()
        if task_clock.remaining_seconds(task.end_at, now) > 0:
            remaining = task_clock.remaining_display(task.end_at, now)
            dialog = ConfirmDialog(
                "Task 해제",
                "아직 종료까지 시간이 남았습니다.\nTask를 해제할까요?",
                confirm_text="해제",
                value_caption="남은시간",
                value="1분 미만" if remaining == "00:00" else remaining,
                note="해제하면 종료 알림을 받지 않습니다.",
                danger=True,
                parent=self.widget,
            )
        else:
            dialog = ConfirmDialog(
                "Task 해제",
                "Task를 해제할까요?",
                confirm_text="해제",
                danger=True,
                parent=self.widget,
            )
        return dialog.exec_over(self.widget)

    def open_settings(self):
        """위젯 우클릭 '설정' / 설정 단축키: 설정창을 띄운다. 이미 떠 있으면 앞으로 올린다."""
        if self._settings is None:
            self._settings = SettingsDialog(self.widget_cfg, f"{APP_NAME} {VERSION}")
            self._settings.shortcuts_changed.connect(self.widget.apply_shortcuts)
            self._settings.appearance_changed.connect(self.apply_appearance)
            self._settings.destroyed.connect(self._on_settings_destroyed)
        self._settings.show_front()

    def _on_settings_destroyed(self):
        self._settings = None

    def _apply_theme(self):
        """설정의 Appearance 값으로 현재 테마와 앱 기본 글꼴(툴팁 등)을 건다."""
        appearance = widget_config.appearance(self.widget_cfg)
        theme.set_current(theme.build(appearance, theme.system_dark()))
        font = QFont(self._base_font)  # 힌팅 설정(PreferNoHinting)은 그대로
        if appearance["font_family"]:
            font.setFamilies([appearance["font_family"], self._base_font.family()])
        QApplication.setFont(font)

    def apply_appearance(self):
        """설정창 Appearance 변경: 위젯을 다시 입힌다. 팝업은 다음에 띄울 때부터 따른다."""
        self._apply_theme()
        self.widget.apply_appearance()

    def _on_color_scheme_changed(self, *_):
        if widget_config.appearance(self.widget_cfg)["theme"] == "system":
            self.apply_appearance()
            if self._settings is not None:
                self._settings.apply_theme()

    def toggle_widget(self, show: bool):
        """트레이 메뉴의 '위젯 보이기' 토글"""
        if show:
            self.widget.show_widget()
        else:
            self.widget.hide_widget()

    def on_tray_activated(self, reason):
        """트레이 아이콘 좌클릭 시 위젯이 보이는 중이면 다른 앱보다 위로 꺼낸다."""
        if reason == QSystemTrayIcon.Trigger:
            self.widget.bring_to_front()

    def on_second_instance(self):
        """이미 실행 중일 때 다시 실행하면(바로가기 등) 위젯을 띄워 다른 앱보다 위로 꺼낸다."""
        if not self.widget.isVisible():
            self.widget.show_widget()  # visibility_changed 로 트레이 체크도 맞춰진다
        self.widget.bring_to_front()

    def sync_widget_toggle_action(self, visible: bool):
        """위젯 쪽에서 숨김/표시가 일어났을 때 트레이 체크박스를 맞춤"""
        self.action_toggle_widget.blockSignals(True)
        self.action_toggle_widget.setChecked(visible)
        self.action_toggle_widget.blockSignals(False)

    def app_close(self):
        """트레이 / 위젯 메뉴의 '종료': 위젯 정지 / 설정 저장 후 종료"""
        self.widget_tick.stop()
        if self._settings is not None:
            self._settings.close()
        self.widget.close()
        widget_config.save_config(self.widget_cfg)
        db.close()
        super().app_close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    # 컬러 이모지는 힌팅을 끄면 테두리가 덜 뭉개진다 (웹 브라우저도 힌팅 없이 그림)
    font = app.font()
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    # Win+. 이모지 패널 입력 보정 (Qt 6.8 이 서로게이트 쌍을 버림 - ui/text_input 참고)
    ime_filter = ImeCharFilter()
    app.installNativeEventFilter(ime_filter)

    if not DEBUG:  # 디버그 앱이 설치/제거를 막지 않도록
        os_win.create_app_mutex()

    window = TaskPinApp()
    sys.exit(app.exec())

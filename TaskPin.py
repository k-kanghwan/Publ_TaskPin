"""Task알림 (TaskPin) - 업무(Task) 시간 관리 + TODO 리마인더 바탕화면 위젯"""

# ---- Nuitka 빌드 옵션 (python -m nuitka TaskPin.py -> build/TaskPin.dist) ----
# 배포는 이 standalone 폴더를 Inno Setup(installer/TaskPin.iss)으로 묶은 설치본만 쓴다.
# 버전을 올릴 때는 version.py 만 고친다. (--product-version 도 거기서 읽고, 설치본은 exe 에서 읽음)
# nuitka-project-set: APP_VERSION = __import__("re").search(r'^VERSION = "(.+)"', open({MAIN_DIRECTORY} + "/version.py", encoding="utf-8").read(), __import__("re").M).group(1)
# nuitka-project: --mode=standalone
# nuitka-project: --output-dir={MAIN_DIRECTORY}/build
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/ico/01_original_navy-coral/icon.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/ico/01_original_navy-coral/icon.svg=ico/01_original_navy-coral/icon.svg
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/ico/03_light-indigo/icon.svg=ico/03_light-indigo/icon.svg
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
import importlib
import os
import sqlite3
import sys
from datetime import datetime

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from manager import (
    db,
    os_win,
    profiles,
    snippets,
    task_clock,
    task_store,
    todo_pages,
    widget_config,
)
from ui import theme
from ui.clock_widget import ClockWidget
from ui.confirm_dialog import ConfirmDialog
from ui.settings_dialog import SettingsDialog
from ui.tag_dialog import TagDialog
from ui.task_picker import TaskPicker
from ui.text_input import ImeCharFilter
from ui.tray_app import TrayApp
from version import VERSION

# VS Code 디버그 실행(.vscode/launch.json): 실제 앱과 분리, 기능별 예제 TODO 페이지(tools/debug_seed)
# (데이터는 launch.json 이 APPDATA 를 .debug_appdata 로 바꿔 분리한다)
DEBUG = os.environ.get("TASKPIN_DEBUG") == "1"
# Task 를 내리는 방식별 화면 문구 (task_store.COMPLETED / RELEASED)
FINISH_VERBS = {task_store.COMPLETED: "완료", task_store.RELEASED: "해제"}
# 설정창 Application "앱 아이콘" (widget_config.APP_ICONS) -> 트레이 / 창 아이콘 (resource_path 기준)
APP_ICONS = {
    "dark": "ico/01_original_navy-coral/icon.svg",
    "light": "ico/03_light-indigo/icon.svg",
}
# 프로필 삭제는 이 문구를 똑같이 입력해야 한다 ("모든 데이터 초기화"처럼)
PROFILE_DELETE_PHRASE = "프로필 삭제"
# 프로필 파일을 열거나 옮기다 나는 오류
PROFILE_ERRORS = (sqlite3.Error, ValueError, OSError)


class TaskPinApp(TrayApp):
    # 단일 인스턴스 ID - 디버그는 설치본이 실행 중이어도 같이 뜨도록 분리
    APP_ID = f"{getpass.getuser()}_TaskPin" + ("_debug" if DEBUG else "")
    # 디버그 실행은 아이콘 색을 달리해 트레이에서 설치본과 구별한다 (빌드에는 넣지 않음)
    if DEBUG:
        TRAY_ICON = "ico/02_graphite-lime/icon.svg"

    def __init__(self):
        super().__init__()

        # ==========================
        # 설정(모든 프로필이 함께 씀) + 프로필(DB 파일 하나 - manager/profiles)
        # 단일 인스턴스를 확인한 뒤에 연다 (처음 한 번 예전 데이터 파일을 프로필 폴더로 옮긴다)
        self.widget_cfg = widget_config.load_config()
        self._profile = self._open_startup_profile()
        if DEBUG and self._seed_debug_examples():
            # 예제가 설정(사용자 태그 / 항상 위)을 고쳐 저장했다 - 위젯이 그 값을 쓰게 다시 읽는다
            self.widget_cfg = widget_config.load_config()

        # ==========================
        # Task 시간 (지금 프로필의 가장 최근 등록 1건)
        self._task = None
        self._shown_task = None  # 위젯에 마지막으로 반영한 Task
        self._notified_task_ids = set()  # 종료 알림을 보낸 Task id
        self._load_task()

        # ==========================
        # 바탕화면 위젯
        self._apply_app_icon()
        # 등록된 명령이 낡았으면 갱신 (디버그에서는 설치본 exe 등록값을 python 명령으로 덮어쓰지 않도록 건너뜀)
        if not DEBUG:
            os_win.sync_autostart_command()
        # 테마는 위젯을 만들기 전에 건다 (위젯 / 팝업은 만들 때 theme.current() 를 읽는다)
        self._base_font = QApplication.font()
        self._apply_theme()
        self.widget = ClockWidget(self.widget_cfg)
        self._settings = None  # 열려 있는 설정창 (한 번에 하나)
        self.widget.set_profile_menu(self._fill_profile_menu)
        self._sync_profile_ui()
        self._picker = None  # 열려 있는 Task 등록 / 수정 창 (한 번에 하나)
        # 등록 창을 확인 없이 닫을 때 적던 (업무명, 상세 업무) - 다음 등록 때 다시 채운다 (실행 중에만)
        self._task_draft = ("", "")

        self.widget.task_register_requested.connect(self.open_task_picker)
        self.widget.task_edit_requested.connect(self.open_task_editor)
        self.widget.task_release_requested.connect(
            lambda: self.finish_task(task_store.RELEASED)
        )
        self.widget.task_clear_requested.connect(
            lambda: self.finish_task(task_store.COMPLETED)
        )
        self.widget.settings_requested.connect(self.open_settings)
        self.widget.quit_requested.connect(self.app_close)
        self.widget.visibility_changed.connect(self.sync_widget_toggle_action)
        self.widget.reminder_due.connect(
            lambda _id, text: self.send_message_info("⏰ 리마인더", text)
        )
        # 등록 / 수정 창이 떠 있는 동안 막힌 위젯을 누르면 그 창을 다시 앞으로
        self.widget.blocked_clicked.connect(self._raise_picker)
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

    @staticmethod
    def _seed_debug_examples() -> bool:
        """디버그 실행: 없는 예제 페이지("🧪 ...")와 예제 프로필을 만든다 (.debug_appdata 일 때만, 위젯을
        만들기 전에). 무엇이든 만들었으면 True. importlib 로 불러 Nuitka 가 tools/ 를 빌드에 넣지 않게 한다."""
        made = importlib.import_module("tools.debug_seed").ensure()
        if made:
            # 이름은 찍지 않는다 - 이모지는 cp949 콘솔에서 깨짐
            print(f"[debug] 예제 {len(made)}개를 만들었습니다", flush=True)
        return bool(made)

    def _load_task(self):
        """지금 프로필의 가장 최근 Task. 이미 끝난 Task 는 알린 것으로 친다 (켜자마자 / 프로필을 바꾸자마자
        종료 알림이 뜨지 않게). Task id 는 프로필(DB)마다 따로 매기므로 알림 기록도 새로 시작한다."""
        self._task = task_store.latest()
        self._notified_task_ids = set()
        if self._task is not None and self._task.end_at <= datetime.now().astimezone():
            self._notified_task_ids.add(self._task.id)

    def open_task_picker(self):
        """위젯의 [등록] 버튼(Task 가 없을 때): 등록 창을 수정 창과 같은 자리([수정] 버튼 위)에 띄운다.
        지난번에 확인 없이 닫은 업무명 / 상세 업무가 있으면 채워 둔다."""
        if self._raise_picker():
            return
        picker = TaskPicker(
            None,
            lambda: snippets.from_config(self.widget_cfg),
            self.widget,
            draft=self._task_draft,
        )
        picker.picked.connect(self.register_task)
        picker.canceled.connect(self._keep_task_draft)
        self._show_picker(picker, self.widget.btn_task_edit)

    def open_task_editor(self):
        """위젯의 [수정] 버튼: 진행 중인 Task 값으로 채운 창을 띄우고, 확인하면 그 행을 고친다."""
        task = self._shown_task
        if task is None or self._raise_picker():
            return
        picker = TaskPicker(
            task, lambda: snippets.from_config(self.widget_cfg), self.widget
        )
        picker.picked.connect(lambda *values: self.update_task(task.id, *values))
        self._show_picker(picker, self.widget.btn_task_edit)

    def _raise_picker(self) -> bool:
        """등록 / 수정 창은 하나만 - 이미 떠 있으면 앞으로 올리고 True"""
        if self._picker is None:
            return False
        self._picker.raise_()
        self._picker.activateWindow()
        return True

    def _show_picker(self, picker: TaskPicker, anchor):
        """등록 / 수정 창을 띄우는 동안 위젯은 끌어 옮기기만 된다 (항목 클릭 / 우클릭 / 단축키 막음).
        "항상 위에 보이기" 설정과 관계없이 위젯과 창을 위에 둔다 - 다른 앱을 보며 적어도 뒤로 숨지 않게."""
        self._picker = picker
        picker.closed.connect(self._on_picker_closed)
        self.widget.set_input_blocked(True)
        self.widget.hold_on_top("picker", True)
        picker.popup_for(anchor)

    def _on_picker_closed(self):
        self._picker = None
        self.widget.set_input_blocked(False)
        self.widget.hold_on_top("picker", False)

    def _keep_task_draft(self, title: str, detail: str):
        """등록 창을 확인 없이 닫음: 적던 내용을 다음 등록 때까지 남긴다 (둘 다 비었으면 비운다)."""
        self._task_draft = (title, detail)

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
        self._task_draft = ("", "")  # 등록했으니 임시저장은 비운다
        self._task = task
        self.tick_widget()

    def update_task(
        self,
        task_id: int,
        title: str,
        detail: str,
        start_at: datetime,
        end_at: datetime,
    ):
        """[수정] 확인: 같은 행을 고친다. 종료를 미래로 바꾸면 종료 알림을 다시 받는다."""
        task = task_store.update(task_id, title, detail, start_at, end_at)
        if task is None:
            self.tray.showMessage(
                "Task 수정", "저장하지 못했습니다.", QSystemTrayIcon.Warning
            )
            return
        if task.end_at <= datetime.now().astimezone():
            self._notified_task_ids.add(task.id)
        else:
            self._notified_task_ids.discard(task.id)
        self._task = task
        self.tick_widget()

    def finish_task(self, kind: str):
        """[완료] / [해제](진행 중일 때의 [등록/해제]): 확인 후 기록은 남기고(내린 방식 포함)
        위젯에서 내린다. 종료 알림도 보내지 않는다."""
        task = self._shown_task
        if task is None or not self._confirm_finish(task, kind):
            return
        if self._picker is not None and self._picker.editing:
            self._picker.close()  # 내린 Task 를 고치던 창은 닫는다
        if not task_store.clear(task.id, kind):
            self.tray.showMessage(
                f"Task {FINISH_VERBS[kind]}",
                "저장하지 못했습니다.",
                QSystemTrayIcon.Warning,
            )
            return
        self._task = None
        self.tick_widget()

    def _confirm_finish(self, task, kind: str) -> bool:
        """종료까지 시간이 남았으면 남은시간을 보여주고, 아니면 완료 / 해제 여부만 묻는다.
        해제는 완료로 기록되지 않는 동작이라 경고색 버튼으로 한 번 더 확인한다."""
        verb = FINISH_VERBS[kind]
        released = kind == task_store.RELEASED
        note = (
            "해제는 완료가 아닌 해제로 기록되고, 종료 알림도 받지 않습니다."
            if released
            else "완료하면 종료 알림을 받지 않습니다."
        )
        now = datetime.now().astimezone()
        if task_clock.remaining_seconds(task.end_at, now) > 0:
            remaining = task_clock.remaining_display(task.end_at, now)
            dialog = ConfirmDialog(
                f"Task {verb}",
                f"아직 종료까지 시간이 남았습니다.\nTask를 {verb}할까요?",
                confirm_text=verb,
                value_caption="남은시간",
                value="1분 미만" if remaining == "00:00" else remaining,
                note=note,
                danger=released,
                parent=self.widget,
            )
        else:
            dialog = ConfirmDialog(
                f"Task {verb}",
                f"Task를 {verb}할까요?",
                confirm_text=verb,
                note=note if released else "",
                danger=released,
                parent=self.widget,
            )
        return dialog.exec_over(self.widget)

    def open_settings(self):
        """위젯 우클릭 '설정' / 설정 단축키: 설정창을 띄운다. 이미 떠 있으면 앞으로 올린다."""
        if self._settings is None:
            self._settings = SettingsDialog(self.widget_cfg, f"{APP_NAME} {VERSION}")
            self._settings.shortcuts_changed.connect(self.widget.apply_shortcuts)
            self._settings.appearance_changed.connect(self.apply_appearance)
            self._settings.config_imported.connect(self.apply_imported_config)
            self._settings.app_icon_changed.connect(self._apply_app_icon)
            self._settings.opacity_changed.connect(self.widget.apply_opacity)
            self._settings.data_reset.connect(self.reload_data)
            self._settings.destroyed.connect(self._on_settings_destroyed)
        self._settings.show_front()

    def _on_settings_destroyed(self):
        self._settings = None

    def reload_data(self, keep_copy: bool = False):
        """DB 가 바뀐 뒤 ("모든 데이터 초기화" / 프로필 바꾸기): 메모리의 Task / 할 일 상태를 그 DB 로 다시 읽는다.
        열린 등록 / 수정 창은 닫고(닫으며 임시저장되는 것까지) 임시저장한 업무명도 버린다.
        keep_copy: 복사해 둔 할 일은 남긴다 (다른 프로필에 붙여넣기)"""
        if self._picker is not None:
            self._picker.close()
        self._task_draft = ("", "")
        self._load_task()
        self.widget.reload_data(keep_copy=keep_copy)
        self.tick_widget()

    # ==========================
    # 프로필 (Obsidian 의 vault 처럼 - DB 파일 하나가 프로필 하나, manager/profiles)
    # ==========================
    def _open_startup_profile(self) -> str:
        """시작: 예전 데이터(taskpin.db)를 기본 프로필로 옮기고, 마지막으로 연 프로필을 연다.
        그 프로필이 깨져 열 수 없으면 열 수 있는 다른 프로필을 열고 트레이로 알린다."""
        cfg = self.widget_cfg
        migrated = profiles.migrate_legacy()
        wanted = profiles.startup_name(cfg.get("profile"))
        others = [name for name in profiles.names() if name != wanted]
        # 모두 열 수 없으면 그대로 열어 오류를 낸다 (예전처럼)
        name = next((n for n in [wanted, *others] if self._can_open(n)), wanted)
        db.connect(profiles.path(name))
        if name != wanted:
            QTimer.singleShot(
                0,
                lambda: self._profile_warning(
                    "프로필",
                    f"'{wanted}' 프로필을 열지 못해 '{name}' 프로필을 열었습니다.",
                ),
            )
        # v0.1.29 까지 설정에 두던 마지막 페이지는 이제 프로필 DB 에 둔다 (옮긴 프로필에만 맞는 id)
        legacy_page = cfg.pop(widget_config.LEGACY_TODO_PAGE_KEY, None)
        if migrated and type(legacy_page) is int:
            todo_pages.set_last_page(legacy_page)
        cfg["profile"] = name
        widget_config.save_config(cfg)
        return name

    @staticmethod
    def _can_open(name: str) -> bool:
        """없는 프로필은 열면서 만든다. 있으면 이 앱의 DB 인지 확인한다."""
        if not os.path.exists(profiles.path(name)):
            return True
        try:
            profiles.check(name)
        except PROFILE_ERRORS:
            return False
        return True

    def _sync_profile_ui(self):
        """헤더 칩(프로필이 둘 이상일 때) / 트레이 툴팁 / 설정창 초기화 설명을 지금 프로필에 맞춘다."""
        many = len(profiles.names()) > 1
        self.widget.set_profile(self._profile, many)
        tip = f"{APP_NAME} {VERSION}" + (" (debug)" if DEBUG else "")
        self.tray.setToolTip(tip + (f"\n프로필: {self._profile}" if many else ""))
        if self._settings is not None:
            self._settings.refresh_profile()

    def _fill_profile_menu(self, menu):
        """좌패널 우클릭 "프로필" 서브메뉴 / 헤더 칩 메뉴 (열 때마다 폴더를 다시 읽는다 - 넣은 .db 도 보임)"""
        existing = profiles.names()
        self._sync_profile_ui()  # 폴더에 파일을 넣거나 지웠으면 칩도 맞춘다
        for name in existing:
            # & 는 메뉴 단축 글자 표시가 되므로 && 로
            act = menu.addAction(name.replace("&", "&&"))
            act.setCheckable(True)
            act.setChecked(name == self._profile)
            act.triggered.connect(lambda _=False, n=name: self.switch_profile(n))
        menu.addSeparator()
        menu.addAction("새 프로필…", self.new_profile)
        menu.addAction("다른 이름으로 저장…", self.save_profile_as)
        menu.addAction("이름 바꾸기…", self.rename_profile)
        act_delete = menu.addAction("삭제…", self.delete_profile)
        act_delete.setEnabled(len(existing) > 1)  # 마지막 한 프로필은 지우지 않는다
        menu.addSeparator()
        menu.addAction("프로필 폴더 열기", self.open_profile_folder)

    def switch_profile(self, name: str) -> bool:
        """그 프로필의 DB 로 바꾸고 Task / 할 일을 다시 읽는다. 바꿨으면(이미 그 프로필이어도) True.
        열 수 없는 파일이면(다른 앱의 DB / 깨짐) 지금 프로필 그대로 두고 알린다."""
        if name == self._profile:
            return True
        try:
            profiles.check(name)
        except PROFILE_ERRORS:
            self._profile_warning(
                "프로필 바꾸기", f"'{name}' 프로필을 열지 못했습니다."
            )
            return False
        # 고치던 할 일은 지금 DB 에 저장해 둔다 (DB 를 바꾼 뒤 저장하면 옛 목록이 새 DB 를 덮어쓴다)
        self.widget.finish_editing()
        if not self._connect_profile(name, "프로필 바꾸기"):
            return False
        self._set_profile(name)
        self.reload_data(keep_copy=True)
        return True

    def _connect_profile(self, name: str, title: str) -> bool:
        """name 프로필의 DB 로 연결을 바꾼다. 못 열면 지금 프로필을 다시 열고 알린다."""
        try:
            db.connect(profiles.path(name))
        except sqlite3.Error:
            db.connect(profiles.path(self._profile))
            self._profile_warning(title, f"'{name}' 프로필을 열지 못했습니다.")
            return False
        return True

    def _set_profile(self, name: str):
        """지금 프로필 이름을 바꾸고 설정에 남긴다 (다음 실행 때 이 프로필부터)."""
        self._profile = name
        self.widget_cfg["profile"] = name
        widget_config.save_config(self.widget_cfg)
        self._sync_profile_ui()

    def _ask_profile_name(
        self, title: str, ok_text: str, name: str, note: str, current=None
    ):
        """프로필 이름 창. 파일 이름으로 쓸 수 없거나 겹치는 이름은 까닭을 보이고 확인을 끈다.
        확인하면 이름, 취소하면 None. current: 이름을 바꾸는 프로필 (자기 이름은 겹침으로 보지 않음)"""
        existing = profiles.names()
        dialog = TagDialog(
            title=title,
            ok_text=ok_text,
            name=name,
            with_color=False,
            placeholder="이름 (예: 업무)",
            max_length=profiles.NAME_MAX,
            snippets_provider=lambda: snippets.from_config(self.widget_cfg),
            note=note,
            validate=lambda text: profiles.name_error(text, existing, current),
            parent=self.widget,
        )
        if not dialog.exec_over(self.widget):
            return None
        name = dialog.name()
        return None if profiles.name_error(name, existing, current) else name

    def new_profile(self):
        """프로필 메뉴 "새 프로필…": 빈 프로필("페이지 1"만)을 만들고 그 프로필로 바꾼다."""
        name = self._ask_profile_name(
            "새 프로필",
            "만들기",
            profiles.unique_name(profiles.names()),
            "빈 할 일 목록과 Task로 시작합니다. 설정은 모든 프로필이 함께 씁니다.",
        )
        if name is None:
            return
        try:
            profiles.create(name)
        except PROFILE_ERRORS:
            self._profile_warning("새 프로필", f"'{name}' 프로필을 만들지 못했습니다.")
            return
        self.switch_profile(name)

    def save_profile_as(self):
        """프로필 메뉴 "다른 이름으로 저장…": 지금 프로필을 그대로 복사해 새 이름으로 저장하고 그 프로필로
        바꾼다 (원래 프로필은 그대로 남는다). 내용이 같으므로 목록은 다시 읽지 않고 연결만 바꾼다."""
        old = self._profile
        name = self._ask_profile_name(
            "다른 이름으로 저장",
            "저장",
            profiles.unique_name(profiles.names()),
            f"'{old}' 프로필의 할 일 · 페이지 · Task 기록을 복사해 새 프로필로 저장하고 "
            "그 프로필로 바꿉니다.",
        )
        if name is None:
            return
        self.widget.finish_editing()
        try:
            profiles.duplicate(name)
        except PROFILE_ERRORS:
            self._profile_warning(
                "다른 이름으로 저장", f"'{name}' 프로필로 저장하지 못했습니다."
            )
            return
        if self._connect_profile(name, "다른 이름으로 저장"):
            self._set_profile(name)

    def rename_profile(self):
        """프로필 메뉴 "이름 바꾸기…": 지금 프로필의 파일 이름을 바꾼다 (닫고 바꾼 뒤 다시 연다)."""
        old = self._profile
        name = self._ask_profile_name(
            "프로필 이름",
            "변경",
            old,
            "프로필 폴더의 파일 이름(이름.db)도 함께 바뀝니다.",
            current=old,
        )
        if name is None or name == old:
            return
        self.widget.finish_editing()
        db.close()
        try:
            profiles.rename(old, name)
        except OSError:
            db.connect(profiles.path(old))
            self._profile_warning("프로필 이름", "파일 이름을 바꾸지 못했습니다.")
            return
        if self._connect_profile(name, "프로필 이름"):
            self._set_profile(name)

    def delete_profile(self):
        """프로필 메뉴 "삭제…": 문구를 입력해 확인한 뒤 목록에서 앞(없으면 뒤) 프로필로 바꾸고 지운다.
        마지막 한 프로필은 지우지 않는다. (파일은 데이터 폴더의 백업 이름으로 옮긴다 - 따로 말하지 않음)"""
        old = self._profile
        target = profiles.neighbor(old, profiles.names())
        if target is None:
            return
        dialog = ConfirmDialog(
            "프로필 삭제",
            f"'{old}' 프로필을 지울까요?\n"
            "할 일 · 페이지 · 삭제 이력 · Task 기록이 모두 사라지고, 앱에서 되돌릴 수 없습니다.",
            confirm_text="삭제",
            note=f"지우면 '{target}' 프로필로 바꿉니다. "
            f"계속하려면 아래에 '{PROFILE_DELETE_PHRASE}'를 입력하세요.",
            danger=True,
            confirm_phrase=PROFILE_DELETE_PHRASE,
            parent=self.widget,
        )
        if not dialog.exec_over(self.widget) or not self.switch_profile(target):
            return
        try:
            profiles.remove(old, datetime.now())
        except OSError:
            self._profile_warning(
                "프로필 삭제", f"'{old}' 프로필 파일을 지우지 못했습니다."
            )
        self._sync_profile_ui()

    @staticmethod
    def open_profile_folder():
        QDesktopServices.openUrl(QUrl.fromLocalFile(profiles.folder()))

    def _profile_warning(self, title: str, message: str):
        self.tray.showMessage(title, message, QSystemTrayIcon.Warning)

    def _apply_theme(self):
        """설정의 Appearance 값으로 현재 테마와 앱 기본 글꼴(툴팁 등)을 건다."""
        appearance = widget_config.appearance(self.widget_cfg)
        theme.set_current(theme.build(appearance, theme.system_dark()))
        self.tray_menu.setStyleSheet(theme.menu_style(theme.current()))
        font = QFont(self._base_font)
        if appearance["font_family"]:
            font.setFamilies([appearance["font_family"], self._base_font.family()])
        QApplication.setFont(font)

    def _apply_app_icon(self):
        """설정의 앱 아이콘(다크 / 라이트)으로 트레이 / 창 아이콘을 바꾼다.
        디버그 실행은 설치본과 구별하도록 늘 TRAY_ICON(graphite-lime)을 쓴다."""
        if not DEBUG:
            self.set_icon(APP_ICONS[widget_config.app_icon(self.widget_cfg)])

    def apply_appearance(self):
        """설정창 Appearance 변경: 위젯을 다시 입힌다. 팝업은 다음에 띄울 때부터 따른다."""
        self._apply_theme()
        self.widget.apply_appearance()

    def apply_imported_config(self, new: dict):
        """설정창 '설정 가져오기': 위젯 / 설정창이 함께 쓰는 cfg 를 제자리에서 바꾸고 모두 다시 적용한다."""
        self.widget_cfg.clear()
        self.widget_cfg.update(new)
        # 설정 파일에는 DB 가 들어가지 않는다 - 다른 PC 의 프로필 이름이 와도 지금 프로필 그대로
        self.widget_cfg["profile"] = self._profile
        widget_config.save_config(self.widget_cfg)
        self.apply_appearance()
        self._apply_app_icon()
        self.widget.apply_shortcuts(widget_config.shortcuts(self.widget_cfg))
        self.widget.reload_config()
        if self._settings is not None:
            self._settings.reload_values()

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

    # Win+. 이모지 패널 입력 보정 (Qt 6.8 이 서로게이트 쌍을 버림 - ui/text_input 참고)
    ime_filter = ImeCharFilter()
    app.installNativeEventFilter(ime_filter)

    if not DEBUG:  # 디버그 앱이 설치/제거를 막지 않도록
        os_win.create_app_mutex()

    window = TaskPinApp()
    sys.exit(app.exec())

"""트레이 아이콘 + 단일 인스턴스

트레이 우클릭 메뉴에는 "위젯 보이기" 토글과 "종료"만 둔다.
(토글 연결과 종료 정리는 TaskPinApp 에서 수행)
"""

import getpass
import sys

from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from manager import paths


TRAY_ICON = "ico/taskpin_icon_A_memo.svg"


def is_already_running(app_id):
    """앱이 이미 실행 중인지 확인하는 함수"""
    socket = QLocalSocket()
    socket.connectToServer(app_id)
    if socket.waitForConnected(100):  # 연결된다면 이미 실행 중
        return True
    socket.abort()
    return False


def register_server(app_id):
    """로컬 서버를 등록하는 함수"""
    server = QLocalServer()
    server.removeServer(app_id)  # 이전에 남은 소켓 제거
    if not server.listen(app_id):
        raise RuntimeError(f"서버를 시작할 수 없습니다: {server.errorString()}")
    return server


def ensure_single_instance(app_id, title: str, msg: str):
    """앱이 단일 인스턴스로 실행되도록 보장하는 함수"""

    if is_already_running(app_id):
        QMessageBox.warning(None, title, msg)
        sys.exit(0)
    return register_server(app_id)


class TrayApp(QWidget):
    APP_ID = f"{getpass.getuser()}_trayapp__"  # 싱글 인스턴스 실행

    def __init__(self):
        super().__init__()

        # 앱이 단일 인스턴스로 실행되도록 보장
        self.server = ensure_single_instance(
            self.APP_ID, "앱 실행중", "현재 앱이 이미 실행중입니다."
        )

        # 트레이 지원 확인
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "오류", "시스템 트레이를 사용할 수 없습니다.")
            sys.exit(1)

        icon_path = paths.resource_path(TRAY_ICON)
        icon = QIcon(icon_path)
        if icon.isNull():
            QMessageBox.critical(None, "오류", f"아이콘 파일이 없습니다: {icon_path}")
            sys.exit(1)
        QApplication.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(icon)

        # 바탕화면 위젯 표시 토글 (연결은 TaskPinApp 에서 수행)
        self.action_toggle_widget = QAction("위젯 보이기", self)
        self.action_toggle_widget.setCheckable(True)

        self.action_quit = QAction("종료", self)
        self.action_quit.triggered.connect(self.app_close)

        self.tray_menu = QMenu()
        self.tray_menu.addAction(self.action_toggle_widget)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_quit)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

    def send_message_info(self, title: str, message: str):
        self.tray.showMessage(title, message, QSystemTrayIcon.Information)

    def app_close(self):
        """종료. 하위 클래스는 정리 작업 후 super().app_close() 를 호출한다."""
        self.tray.hide()
        self.close()
        QApplication.quit()

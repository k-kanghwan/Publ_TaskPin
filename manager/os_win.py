"""Windows 전용 코드 모음

저장 경로 / 자동 실행(winreg) / 창 z-order(Win32 SetWindowPos) / 설치 프로그램용 mutex 를
이 모듈에만 둔다. macOS 를 추가할 때는 같은 함수를 가진 모듈을 하나 더 만들면 된다.
"""

import ctypes
import os
import sys
import winreg
from ctypes import wintypes

APP_ID = "TaskPin"  # 폴더명 / 레지스트리 값 이름 / mutex 이름 (ASCII 내부 식별자)


# ==================================================
# 저장 경로
# ==================================================
def user_data_dir() -> str:
    """사용자 데이터 폴더: %APPDATA%\\TaskPin"""
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming"
    )
    return os.path.join(base, APP_ID)


# ==================================================
# Win32 z-order
# ==================================================
# 표시 중인 창을 Bottom -> Top 힌트로 바꿔도 Qt(6.8)가 WS_EX_TOPMOST 를
# 설정하지 않으므로 SetWindowPos 로 직접 z-order 를 맞춘다.
# argtypes 미지정 시 64bit 에서 HWND(-1) 전달이 실패한다.
_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_user32.AllowSetForegroundWindow.restype = wintypes.BOOL

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
HWND_BOTTOM = 1
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE


def set_z_order(hwnd: int, insert_after: int):
    _user32.SetWindowPos(hwnd, wintypes.HWND(insert_after), 0, 0, 0, 0, SWP_FLAGS)


def foreground_window():
    return _user32.GetForegroundWindow()


def is_own_window(hwnd) -> bool:
    """이 프로세스(위젯/메뉴/팝업 등)의 창인지"""
    if not hwnd:
        return False
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 20H1 이상


def set_dark_title_bar(hwnd: int, dark: bool = True):
    """제목줄을 앱 테마에 맞춰 어둡게 / 밝게 (Windows 앱 모드와 관계없이). 실패는 무시한다."""
    value = ctypes.c_int(1 if dark else 0)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except OSError:
        pass


ASFW_ANY = 0xFFFFFFFF


def allow_set_foreground():
    """이 프로세스가 가진 전경 창 권한을 다른 프로세스에 넘긴다.
    백그라운드에서 돌던 기존 앱은 Windows 전경 잠금 때문에 스스로 창을 활성화하지 못하므로,
    사용자가 방금 실행한(전경 권한이 있는) 두 번째 실행이 대신 허락해 준다."""
    _user32.AllowSetForegroundWindow(ASFW_ANY)


# ==================================================
# IME 문자 메시지 (Win+. 이모지 패널)
# ==================================================
# 이모지 패널은 고른 이모지를 WM_IME_CHAR 로 UTF-16 코드 단위 하나씩 보낸다.
# Qt 6.8 은 BMP 글자는 넣지만 서로게이트 쌍(🚀 = D83D DE80)은 버리므로
# ui/text_input.ImeCharFilter 가 이 메시지를 대신 받아 입력칸에 넣는다.
WM_CHAR = 0x0102
WM_IME_CHAR = 0x0286


def char_message(message_ptr: int):
    """네이티브 메시지가 WM_CHAR / WM_IME_CHAR 이면 (메시지, UTF-16 코드 단위), 아니면 None"""
    msg = wintypes.MSG.from_address(message_ptr)
    if msg.message in (WM_CHAR, WM_IME_CHAR):
        return msg.message, msg.wParam & 0xFFFF
    return None


class ImeCharDecoder:
    """문자 메시지를 Qt 대신 받을지 정하고, 서로게이트 쌍을 한 글자로 합친다.

    - WM_IME_CHAR 는 모두 받는다. BMP 글자(ZWJ, 변형 선택자)도 같은 경로로 넣어야
      👨‍👩‍👧 같은 이모지 시퀀스의 순서가 섞이지 않는다.
    - WM_CHAR 는 서로게이트만 받는다. 일반 글자는 Qt 키 이벤트(단축키 등)로 둔다.
    """

    def __init__(self):
        self._high = None  # 짝을 기다리는 상위 서로게이트

    def feed(self, message: int, unit: int):
        """Returns (Qt 에 넘기지 않고 가로챌지, 넣을 문자열 또는 None)"""
        if 0xD800 <= unit <= 0xDBFF:
            self._high = unit
            return True, None
        if 0xDC00 <= unit <= 0xDFFF:
            high, self._high = self._high, None
            if high is None:  # 짝 없는 하위 서로게이트는 버린다
                return True, None
            return True, chr(0x10000 + ((high - 0xD800) << 10) + (unit - 0xDC00))
        self._high = None
        if message == WM_IME_CHAR:
            return True, chr(unit)
        return False, None


# ==================================================
# 설치 프로그램(Inno Setup AppMutex)이 실행 여부를 확인하는 mutex
# ==================================================
_kernel32 = ctypes.windll.kernel32
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE

_app_mutex = None  # 프로세스가 끝날 때까지 핸들을 유지해야 한다


def create_app_mutex():
    global _app_mutex
    if _app_mutex is None:
        _app_mutex = _kernel32.CreateMutexW(None, False, APP_ID)


# ==================================================
# 윈도우 시작 시 자동 실행
# ==================================================
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# 개발 환경(컴파일 전)에서 실행할 메인 스크립트
_MAIN_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "TaskPin.py",
)


def _launch_command() -> str:
    if "__compiled__" in globals():  # Nuitka 빌드
        return f'"{os.path.abspath(sys.argv[0])}"'

    # 개발 환경: python.exe 는 콘솔 서브시스템이라 실행 시 터미널 창이 뜬다.
    # 콘솔이 없는 pythonw.exe 를 우선 사용한다.
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{_MAIN_SCRIPT}"'


def get_autostart_command() -> str:
    """레지스트리에 등록된 자동 실행 명령 문자열. 미등록이면 빈 문자열"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
        return value or ""
    except OSError:
        return ""


def is_autostart_enabled() -> bool:
    return bool(get_autostart_command())


def set_autostart(enable: bool) -> bool:
    """자동 실행 등록/해제. 성공 여부를 반환한다."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enable:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_ID)
                except FileNotFoundError:
                    pass  # 이미 등록되어 있지 않음
        return True
    except OSError as e:
        print(f"자동 실행 설정 실패: {e}")
        return False


def sync_autostart_command() -> bool:
    """
    이미 등록된 자동 실행 명령이 낡았으면 현재 값으로 갱신한다.
    (레지스트리 값은 토글 시점에 문자열로 박히므로, 설치 위치가 바뀌어도
     기존 등록값은 그대로 남아있기 때문)

    미등록 상태면 아무것도 하지 않는다 - 꺼둔 자동 실행을 멋대로 켜지 않기 위함

    Returns
    -------
    bool : 실제로 갱신했으면 True
    """
    current = get_autostart_command()
    if not current or current == _launch_command():
        return False
    return set_autostart(True)


if __name__ == "__main__":
    print(f"데이터 폴더     : {user_data_dir()}")
    print(f"실행 커맨드     : {_launch_command()}")
    print(f"자동 실행 여부  : {is_autostart_enabled()}")

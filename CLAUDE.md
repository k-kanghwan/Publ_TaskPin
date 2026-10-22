# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

- 기획 단계. 소스 코드·의존성 파일·빌드 스크립트가 아직 없다. 요구사항 원본은 `PRD.md`이고, 기능 판단은 PRD를 따른다.
- 앱 표시명은 **Task알림**(창 제목·exe 표시명). 폴더명·자동 실행 레지스트리 키·단일 인스턴스 ID 같은 내부 식별자는 ASCII **TaskPin**을 쓴다.
- 앱 아이콘은 `ico/taskpin_icon_A_memo.svg`로 임시 지정. `img/image.png`는 참고 앱 화면이라 PRD의 FE 변경사항이 반영되지 않았다.
- 스택: Python 3.11.4 이상, PySide6, SQLite(내장 `sqlite3`), Nuitka onefile. 버전은 Semantic Versioning.
- 지금은 Windows 전용. 자동 실행(`winreg`)·창 z-order(`ctypes` Win32)·저장 경로처럼 OS에 묶인 코드는 한 모듈에 모아, 나중에 macOS를 추가할 수 있게 한다.

## 참고 소스: `C:\Users\kh.Cha\Documents\MyProject\Priv_WimsClockManager\`

이 프로젝트의 위젯/TODO 부분을 가져오고 사내 서버(WIMS) 연동은 뺀다. PySide6 기반.

- 가져올 것
  - `ui/clock_widget.py` — 좌측 시간 패널 + 우측 TODO 위젯, 투명도 슬라이더, 리사이즈, 가로/세로 모드, 항상 위/아래(Win32 `SetWindowPos`)
  - `ui/todo_panel.py`, `ui/reminder_picker.py`, `ui/reminder_popup.py` — TODO 목록, `(@` 리마인더 입력, 알림 팝업/스누즈
  - `manager/todo_store.py` — 리마인더 토큰 처리(`parse_reminder`, `strip_reminder`, `due_at`, `is_due` 등). 텍스트 안 `(@YYYY-MM-DD HH:mm)` 토큰이 리마인더의 유일한 기준 데이터. JSON 저장 부분(`load_todos`/`save_todos`)은 SQLite로 바꾼다.
  - `manager/widget_config.py` — 위젯 설정 저장 + `winreg` 자동 실행. `sys.frozen` 판별은 PyInstaller 기준이라 Nuitka에 맞게 고쳐야 한다.
  - `ui/tray_app.py` — 트레이 + `QLocalServer` 단일 인스턴스, `ui/theme.py` — 색/폰트 상수
- 뺄 것: `manager/wims_driver.py`(Selenium), `manager/secure.py`, `ui/login_widget.py`, `ServerTimeWorker`, 출근하기/퇴근하기, 이석·"출근중" 표시, `src/wims_info.json`, `WimsClockManager.spec`(PyInstaller)
- 메뉴 정리
  - 트레이 우클릭 메뉴(`ui/tray_app.py`)에는 "위젯 보이기" 토글과 종료만 남긴다.
  - 위젯 우클릭 메뉴(`ClockWidget.contextMenuEvent`)에서는 새로고침·WIMS 바로가기·로그인 정보를 뺀다.

## 참고 소스와 달라지는 규칙 (PRD 기준)

- 시간은 로컬 현재시간 기준. 첫 실행 때 입력받는 값은 없다.
- 라벨 변경: "출근" → "시작", "퇴근" → "종료", "남은 근무시간" → "남은시간". 라벨은 고정이다(편집 불가).
- 좌측 패널은 한 번에 한 업무(Task)의 시간만 관리한다. 우측 TODO 리스트는 이와 별개로, 기존 기능 그대로 둔다.
  - "Task 시간 등록" 버튼으로 시작시간과 소요 시간을 고른다. 시작시간은 기본값이 현재시간이고 15분 단위로 고른다.
  - 등록 전에는 시작이 `--:--`. 종료 = 시작 + 소요 시간. 남은시간이 0을 지나면 초과 시간을 `+`로 표시한다.
- 더블클릭으로 편집할 수 있는 곳은 사용자 이름 하나뿐이다.

## 데이터 저장 / 경로

- 사용자 데이터 위치: `%APPDATA%\TaskPin\`
  - `config.json` — 위젯 설정(위치·크기·투명도·모드 등), 사용자 이름
  - `taskpin.db` — SQLite: TODO, 정리된 완료 항목, Task 시간 등록 정보
- "완료 항목 정리"(`TodoPanel.clear_done`)는 행을 지우지 않고 보관 상태로 바꾼다.
- 참고 소스처럼 `os.chdir(BASE_DIR)` 후 CWD 기준 `src/*`에 쓰면 안 된다. Nuitka onefile은 실행할 때 `{TEMP}/onefile_{PID}_{TIME}`에 풀렸다가 지워진다.
- 번들 리소스(아이콘 등)는 `os.path.dirname(__file__)` 기준으로 찾는다. exe가 있는 위치는 `sys.argv[0]` 또는 `__compiled__.containing_dir` 기준. PyInstaller의 `sys._MEIPASS`는 쓰지 않는다.
- 폰트/색상/테마 설정은 PRD에서 "예정" 항목이다. 지금은 나중에 붙일 수 있는 구조만 만든다.

## 빌드 (Nuitka)

- `--mode=standalone`으로 먼저 동작을 확인한 뒤 `--mode=onefile`로 바꾼다(Nuitka 공식 권장 순서).
- PySide6는 `--enable-plugin=pyside6`로 넣는다. 콘솔은 `--windows-console-mode=disabled`.
- Nuitka는 교차 빌드를 지원하지 않는다. macOS 빌드는 macOS에서 해야 한다.

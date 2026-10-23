# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

- v0.1.0 구현 완료(계획: `.claude/plans/init-todo.md`). 요구사항 원본은 `PRD.md`이고, 기능 판단은 PRD를 따른다.
- 앱 표시명은 **Task알림**(창 제목·exe 표시명). 폴더명·자동 실행 레지스트리 키·단일 인스턴스 ID·mutex 같은 내부 식별자는 ASCII **TaskPin**을 쓴다.
- 앱 아이콘 원본은 `ico/taskpin_icon_A_memo.svg`(임시 지정). exe/설치본용 `ico/taskpin.ico`는 `python tools/make_ico.py`로 다시 만든다. `img/image.png`는 참고 앱 화면이라 PRD의 FE 변경사항이 반영되지 않았다.
- 스택: Python 3.11.4 이상, PySide6, SQLite(내장 `sqlite3`), Nuitka standalone + Inno Setup 설치본. 버전은 Semantic Versioning.
- 지금은 Windows 전용. 자동 실행(`winreg`)·창 z-order(`ctypes` Win32)·저장 경로·mutex처럼 OS에 묶인 코드는 `manager/os_win.py`에만 둔다(나중에 macOS 모듈 추가).

## 명령

```bash
pip install -r requirements-dev.txt          # PySide6, pytest, nuitka, watchfiles
python TaskPin.py                            # 실행 (트레이 + 위젯)
pytest                                       # 전체 테스트 (Qt 없이 실행)
pytest tests/test_task_clock.py::test_floor_slot   # 단일 테스트
python -m nuitka TaskPin.py                  # standalone 빌드 -> build/TaskPin.dist/Task알림.exe
iscc installer\TaskPin.iss                   # 설치본 -> dist/TaskPin-<버전>-setup.exe (Inno Setup 6)
```

- 빌드 옵션은 `TaskPin.py` 맨 위 `# nuitka-project:` 주석에 있다. 버전을 올릴 때는 거기의 `--product-version`과 `VERSION`을 같이 고친다. 설치본 버전은 exe에서 읽는다.
- 앱을 띄워 확인할 때 실제 데이터를 건드리지 않으려면 `APPDATA` 환경변수를 임시 폴더로 바꿔 실행한다(`os_win.user_data_dir()`가 이 값을 따른다). 이때 user site-packages(`%APPDATA%\Python`)도 함께 사라지므로 `PYTHONUSERBASE`를 원래 `%APPDATA%\Python`으로 지정한다(`anyio` 등 `pip --user` 패키지).
- VS Code F5(`.vscode/launch.json`): "저장 시 재시작"은 `tools/dev_run.py`(watchfiles `run_process`)가 `.py` 저장마다 앱을 다시 띄운다. 두 구성 모두 `APPDATA=.debug_appdata`, `TASKPIN_DEBUG=1`(위젯 항상 위, 단일 인스턴스 ID 분리, 자동 실행 레지스트리 갱신·mutex 생략)로 실행한다.

## 구조

- `TaskPin.py` — `TaskPinApp(TrayApp)`: 위젯 연결, 1초 tick(현재시간·남은시간·Task 종료 트레이 알림 1회), Task 등록
- `manager/` — Qt 없는 로직: `task_clock`(15분 단위·남은시간 계산), `task_store`/`todo_store`(SQLite), `db`(연결 1개, `PRAGMA user_version` 마이그레이션), `widget_config`(config.json), `paths`, `os_win`
- `ui/` — `clock_widget`(좌측 Task 패널 + TODO 배치, "멍청한 뷰"), `task_picker`(등록 팝업), `todo_panel`/`reminder_*`(참고 소스 이식), `tray_app`, `theme`

## 참고 소스: `C:\Users\kh.Cha\Documents\MyProject\Priv_WimsClockManager\`

이 프로젝트의 위젯/TODO 부분을 가져오고 사내 서버(WIMS) 연동은 뺐다(이식 완료). 아래는 이식 기준으로 남겨 둔다.

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
  - "Task 등록" 버튼으로 업무명(선택)·시작시간·소요 시간을 고른다. 시작시간은 기본값이 현재시간이고 15분 단위로 고른다. "Task 해제"는 확인 창(`ui/confirm_dialog.py`, 시간이 남았으면 남은시간 표시)을 거친 뒤 기록을 남기고(`tasks.cleared_at`) 위젯에서만 내린다.
  - 좌측 하단 배치: 업무명 배지(가운데 정렬·테두리, 비어 있으면 숨김) → [Task 등록][Task 해제] → 투명도 슬라이더
  - 등록 창(`TaskPicker`)은 `Qt.Popup`이 아니라 활성화되는 Tool 창이다. Windows에서 Popup은 전경 창이 되지 않아 IME가 붙지 않는다(한글 입력 불가).
  - 등록 전에는 시작이 `--:--`. 종료 = 시작 + 소요 시간. 남은시간이 0을 지나면 초과 시간을 `+`로 표시한다.
- 더블클릭으로 편집할 수 있는 곳은 사용자 이름 하나뿐이다.

## 데이터 저장 / 경로

- 사용자 데이터 위치: `%APPDATA%\TaskPin\`
  - `config.json` — 위젯 설정(위치·크기·투명도·모드 등), 사용자 이름
  - `taskpin.db` — SQLite: TODO, 정리된 완료 항목, Task 시간 등록 정보
- "완료 항목 정리"(`TodoPanel.clear_done`)는 행을 지우지 않고 보관 상태로 바꾼다.
- 참고 소스처럼 `os.chdir(BASE_DIR)` 후 CWD 기준 `src/*`에 쓰면 안 된다. 자동 실행 시 CWD는 system32이고, 설치 폴더(`%LOCALAPPDATA%\Programs\TaskPin`)는 재설치·제거 때 바뀐다.
- 번들 리소스(아이콘 등)는 `paths.resource_path()`(`__file__` 기준)로 찾는다. 컴파일 여부는 `"__compiled__" in globals()`, exe 경로는 `sys.argv[0]` 기준. PyInstaller의 `sys._MEIPASS`는 쓰지 않는다.
- 폰트/색상/테마 설정은 PRD에서 "예정" 항목이다. 지금은 나중에 붙일 수 있는 구조만 만든다.

## 빌드 / 배포 (Nuitka standalone + Inno Setup)

- 배포는 설치본만 만든다. onefile은 쓰지 않는다(시작 지연·백신 오탐·자동 실행 경로가 불안정하기 때문).
- Nuitka: `--mode=standalone`, PySide6는 `--enable-plugin=pyside6`(iconengines/imageformats 플러그인이 자동 포함되어 SVG 트레이 아이콘이 보인다). 콘솔은 `--windows-console-mode=disable`(`disabled` 아님).
- 설치본(`installer/TaskPin.iss`, UTF-8 BOM으로 저장)
  - 사용자 단위로 설치한다(`PrivilegesRequired=lowest`, `{localappdata}\Programs\TaskPin`).
  - `AppMutex=TaskPin`으로 실행 중이면 설치·제거를 막는다(앱은 `os_win.create_app_mutex()`).
  - 제거할 때 `HKCU\...\Run\TaskPin` 값만 지우고 `%APPDATA%\TaskPin` 데이터는 남긴다.
  - `AppId` GUID는 바꾸지 않는다.
- Inno Setup 6.7 이상은 컴파일러가 "Non-commercial use only"로 표시된다. 상업적으로 배포하려면 라이선스를 확인해야 한다.
- Nuitka는 교차 빌드를 지원하지 않는다. macOS 빌드는 macOS에서 해야 한다.

# 구현 계획: Task알림 (TaskPin) v0.1.0

## Context

`PRD.md` 기준으로 Windows 데스크톱 위젯 앱을 처음부터 만든다. 저장소에는 아직 코드가 없다(커밋 1개, PRD/CLAUDE/아이콘만 있음).

방식: 참고 소스 `Priv_WimsClockManager`의 위젯·TODO·리마인더·트레이 코드를 가져오고, 사내 서버(WIMS) 연동을 걷어낸다. 좌측 패널은 "Task 시간 등록" 방식으로 바꾼다.

검토 중 사용자가 정한 것:

- **등록 팝업 구성**: 업무명(비워도 됨) / 시작시간 / 소요시간 / 종료시간
  - 시작시간: 15분 단위. 기본값은 현재시간을 15분 단위로 내린 값(09:37 → 09:30)
  - 소요시간을 고르면 종료시간을 계산하고, 종료시간을 고르면 소요시간을 계산한다(둘 다 15분 단위 콤보)
- **업무명 표시**: 투명도 슬라이더 바로 위. 비어 있으면 숨긴다.
- **종료 알림**: 종료시간이 되면 트레이 알림을 한 번 띄운다.

## 폴더 구조

참고 소스의 `manager/`·`ui/` 구조를 그대로 따른다.

```
TaskPin.py               # 진입점: APP_NAME="Task알림", VERSION="0.1.0", Nuitka 빌드 옵션 주석, TaskPinApp(TrayApp)
requirements.txt         # PySide6
requirements-dev.txt     # pytest, nuitka
ico/taskpin.ico          # tools/make_ico.py로 SVG에서 만든 exe 아이콘
tools/make_ico.py        # QSvgRenderer로 A_memo.svg를 .ico로 변환(1회 실행)
manager/
  os_win.py              # Windows 전용 코드는 전부 여기: user_data_dir(%APPDATA%\TaskPin), 자동 실행(winreg), SetWindowPos z-order, 전경 창 판별
  paths.py               # resource_path(): __file__ 기준 번들 리소스 경로 / data_path(name): os_win.user_data_dir() 아래 경로
  widget_config.py       # 참고 소스 기반 config.json 저장·불러오기 + "user_name" 키 추가. 자동 실행은 os_win에 맡김
  db.py                  # sqlite3 연결(taskpin.db), PRAGMA user_version으로 스키마 버전 관리, 테스트용 경로 주입 가능
  todo_store.py          # 참고 소스의 리마인더 토큰 함수는 그대로 두고, 저장 부분만 SQLite로 교체
  task_store.py          # Task 등록 기록 저장/불러오기, 현재 Task 판정
  task_clock.py          # Qt 없는 순수 계산(15분 내림, 시작/소요/종료 상호 계산, 남은시간 문자열)
ui/
  theme.py               # 참고 소스 복사 + 콤보박스/입력칸 공통 스타일(POPUP_FORM_STYLE) 추출
  reminder_picker.py     # 참고 소스 복사. 콤보 스타일만 theme.POPUP_FORM_STYLE을 쓰게
  reminder_popup.py      # 참고 소스 복사
  todo_panel.py          # 참고 소스 복사. clear_done만 보관(archive) 처리로 변경
  task_picker.py         # 신규: Task 시간 등록 팝업
  clock_widget.py        # 참고 소스 기반으로 좌측 패널 수정, Win32 코드는 os_win으로 이동
  tray_app.py            # 참고 소스에서 축소: 위젯 보이기 토글 + 종료만
tests/                   # pytest: task_clock / todo_store / task_store
```

## 단계별 작업

### 1단계. 앱 골격 (트레이 + 빈 위젯이 뜨는 상태)

- `manager/os_win.py`
  - `clock_widget.py:83-118`의 `_user32` 설정, `_set_z_order`, `_is_own_window`, HWND 상수를 옮긴다.
  - `widget_config.py:69-134`의 자동 실행 함수를 옮긴다.
  - 레지스트리 항목 이름은 `"TaskPin"`.
- `_launch_command()`를 Nuitka 기준으로 바꾼다.
  - 컴파일된 실행 파일인지는 `"__compiled__" in globals()`로 판별한다.
  - exe 경로는 `os.path.abspath(sys.argv[0])`.
  - 개발 환경에서는 기존처럼 pythonw.exe로 `TaskPin.py`를 실행한다.
- `paths.py`: `os.chdir(BASE_DIR)`와 CWD 기준 `src/` 경로는 모두 없앤다(`WimsClockManager.py:816-821` 방식 폐기).
- `TaskPin.py`
  - `QApplication.setQuitOnLastWindowClosed(False)`를 켠다.
  - `TaskPinApp(TrayApp)`이 위젯을 만들고 연결한다. `WimsClockManager.py:245-276`의 연결 부분만 가져온다.
  - 단일 인스턴스 ID는 `f"{getpass.getuser()}_TaskPin"`.
- `ui/tray_app.py`
  - 남길 것: `ensure_single_instance`와 함께 `action_toggle_widget`("위젯 보이기"), `action_quit`("종료")
  - 뺄 것: 프로필, 현재 시간, 새로고침, 상태/시간 정보, 출퇴근, WIMS, 로그인 정보, `refresh_tray_context`의 `NotImplementedError`
  - 트레이 아이콘은 `resource_path("ico/taskpin_icon_A_memo.svg")`, 툴팁은 `"Task알림 0.1.0"`.
- 가져오지 않을 것
  - `WimsClockManager.py`의 서버·Selenium·로그인 관련 코드 전부
  - `pyperclip`
  - **176-177행 개인 비밀번호 클립보드 복사 코드**: 비밀번호가 코드에 그대로 적혀 있으므로 절대 옮기지 않는다.

### 2단계. 위젯·TODO 가져오기

- `theme.py`, `reminder_picker.py`, `reminder_popup.py`, `todo_panel.py`를 복사한다.
- `clock_widget.py` 수정
  - 시그널 정리: `clock_in/out_requested`, `refresh_requested`, `login_info_requested`, `open_url_requested`를 뺀다. `quit_requested`, `visibility_changed`, `reminder_due`는 남기고 `task_register_requested`를 새로 둔다.
  - 우클릭 메뉴(`contextMenuEvent`)에 남길 것: 완료 항목 정리, 가로/세로 모드, 위치/크기 잠금, 윈도우 시작 시 실행, 위젯 숨기기, 종료.
  - 좌측 패널 변경
    - 헤더: `status_dot`과 `status_label`(출근중)을 뺀다. `name_label`만 둔다.
    - `server_label` → `현재시간  HH:MM:SS`
    - `remaining_caption`은 항상 "남은시간". 라벨은 고정이므로 시간이 넘어가도 문구는 그대로 두고, 글자색(TEXT_WARN)과 `+`로만 초과를 표시한다.
    - `in_label`/`out_label` → `시작 --:--` / `종료 --:--`
    - `ext_label`(이석)은 뺀다.
    - `controls_box` 맨 위, 투명도 슬라이더 위에 `task_title_label`을 둔다. 업무명이 비어 있으면 숨긴다. 세로/가로 모드 모두 같은 위치다.
    - 출근하기/퇴근하기 두 버튼 → 폭 전체를 쓰는 `Task 시간 등록` 버튼 하나.
  - `apply_state(...)`를 `apply_task(task | None)`과 `set_user_name(name)`으로 바꾼다. `set_clock(now_text, remaining_text)`는 그대로 둔다.
- 1초마다 갱신하는 타이머(`WimsClockManager.py:273-314`의 `tick_widget`)는 서버시간 대신 `datetime.now()`를 쓴다. 남은시간 문자열은 `task_clock.remaining_display()`로 만든다(`WimsClockManager.py:779-793` 로직 이식).

### 3단계. SQLite 저장

- `db.py`
  - `connect(path=None)`: 기본 경로는 `data_path("taskpin.db")`. 연결은 하나만 열어서 계속 쓴다. 모든 작업은 UI 스레드에서만 한다.
  - `user_version`이 0이면 아래 스키마를 만든다.

  ```sql
  CREATE TABLE todos (id TEXT PRIMARY KEY, text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
    created TEXT, snooze_until TEXT, fired TEXT, position INTEGER NOT NULL, archived_at TEXT);
  CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL, end_at TEXT NOT NULL, created_at TEXT NOT NULL);
  ```

- `todo_store.py`
  - 그대로 둘 것: `new_item`, `_normalize`, `parse_reminder`, `format_token`, `strip_reminder`, `due_at`, `due_key`, `is_due`, `to_html`, `REMINDER_RE`
  - `load_todos()`: `archived_at IS NULL`인 행을 `position` 순서로 dict 목록으로 돌려준다(기존 dict 키 그대로).
  - `save_todos(items)`: 트랜잭션 하나로 처리한다.
    - 화면 목록에 없는 활성 행은 지운다(사용자가 삭제한 항목).
    - 목록의 항목은 순서를 position에 넣어 저장한다(있으면 갱신, 없으면 추가).
    - 보관된 행은 건드리지 않는다.
  - `archive_items(ids)` 추가: `archived_at`에 현재시각을 넣는다.
  - TodoPanel은 지금처럼 메모리 목록을 통째로 저장하는 방식을 유지하므로 `todo_panel.py`는 거의 그대로 쓴다.
- `TodoPanel.clear_done`(`todo_panel.py:409`): 완료된 항목 id로 `todo_store.archive_items`를 먼저 호출한 뒤, 기존처럼 목록에서 빼고 다시 그린다.
- `widget_config.py`: `CONFIG_PATH`는 `data_path("config.json")`. `DEFAULT_CONFIG`에 `"user_name": ""`를 추가한다.

### 4단계. Task 시간 등록

- `task_clock.py` (순수 함수)
  - `floor_slot(dt)`: 15분 단위로 내림
  - `end_from(start, minutes)`
  - `minutes_between(start, end)`: 종료가 시작 이전이면 다음 날로 본다.
  - `remaining_display(end, now)`: 남았으면 `HH:MM`, 지났으면 `+HH:MM`, Task가 없으면 `--:--`
  - 상수: `STEP_MIN=15`, `MAX_DURATION_MIN=12*60`, `DEFAULT_DURATION_MIN=60`
- `task_store.py`
  - `register(title, start_at, end_at)`: 새 행을 추가한다(기록이 남음).
  - `current_task(now)`: 가장 최근 행을 돌려준다. 단, 시작 날짜가 오늘이 아니고 종료도 이미 지났으면 None(`--:--`). 전날 끝난 Task가 다음 날까지 계속 표시되는 것을 막기 위함이다.
- `ui/task_picker.py`: `TaskPicker(QFrame, Qt.Popup)`. `ReminderPicker`와 같은 다크 팝업·둥근 모서리 방식을 쓴다.
  - 업무명: `QLineEdit`, 비워도 됨
  - 시작: `QComboBox`, 00:00~23:45 (15분 단위). 기본값은 `floor_slot(now)`. 이미 등록된 Task를 다시 열면 그 값으로 채운다.
  - 소요: `QComboBox`, 0:15~12:00 (15분 단위). 기본값 1:00.
  - 종료: `QComboBox`, 시작+15분 ~ 시작+12시간의 시각 목록. 자정을 넘는 항목은 `(+1)`로 표시한다.
  - 동기화는 `blockSignals`로 서로 다시 부르지 않게 한다.
    - 소요를 바꾸면 종료를 다시 계산한다.
    - 종료를 바꾸면 소요를 다시 계산한다.
    - 시작을 바꾸면 소요는 그대로 두고 종료 목록을 다시 만든다.
  - 확인 시 `picked(title, start_dt, end_dt)` 시그널을 보낸다. Enter는 확인, Esc는 취소.
  - 위치는 `Task 시간 등록` 버튼 위쪽에 띄우고 화면 안쪽으로 맞춘다.
- 종료 알림(트레이 알림 한 번)
  - 1초 타이머에서 `now >= end_at`이 되는 순간 `tray.showMessage("Task 종료", title or "등록한 Task 시간이 끝났습니다")`를 띄운다.
  - 이미 알린 Task id는 메모리에 기억한다.
  - 앱을 켤 때 이미 끝난 Task는 알린 것으로 처리해, 켜자마자 알림이 뜨지 않게 한다.

### 5단계. 사용자 이름 편집

- `name_label`을 더블클릭하면 같은 자리에 `QLineEdit`가 뜬다. Enter나 포커스 아웃이면 저장, Esc면 취소.
- 저장은 config의 `user_name`. 값이 비어 있으면 흐린 색(TEXT_DIM)으로 "이름"을 보여준다.
- 더블클릭 편집은 이 라벨에만 둔다.

### 6단계. 빌드 (Nuitka)

`TaskPin.py` 맨 위에 빌드 옵션 주석을 둔다.

```
# nuitka-project-if: os.getenv("TASKPIN_STANDALONE", "no") == "yes":
#    nuitka-project: --mode=standalone
# nuitka-project-else:
#    nuitka-project: --mode=onefile
#    nuitka-project: --onefile-tempdir-spec={CACHE_DIR}/TaskPin/0.1.0
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --windows-console-mode=disabled
# nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/ico/taskpin.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/ico/taskpin_icon_A_memo.svg=ico/taskpin_icon_A_memo.svg
# nuitka-project: --product-name=Task알림
# nuitka-project: --product-version=0.1.0
# nuitka-project: --output-filename=Task알림.exe
```

- 먼저 `TASKPIN_STANDALONE=yes`로 standalone을 빌드해 SVG 트레이 아이콘이 보이는지 확인한다(Qt iconengines/imageformats 플러그인 포함 여부). 아이콘이 안 보이면 `--include-qt-plugins=iconengines`를 추가한다.
- 그다음 onefile을 빌드한다.

### 7단계. 마무리

- `CLAUDE.md`에 실제 명령을 추가한다: 실행, 전체 테스트, 단일 테스트, standalone/onefile 빌드. "기획 단계" 문구도 고친다.

## 테스트 (pytest, Qt 없이 실행)

- `tests/test_task_clock.py`: 15분 내림, 소요→종료/종료→소요 계산, 자정 넘김, `+HH:MM` 표시, 경계값(정확히 0초)
- `tests/test_todo_store.py`: 임시 DB 경로로 확인
  - `save_todos` 후 `load_todos`가 같은 순서로 돌아오는지
  - 화면 목록에서 뺀 항목이 삭제되는지
  - `archive_items`로 보관한 항목이 `load_todos`에서 빠지고 DB에는 남는지
  - 다음 `save_todos` 뒤에도 보관 행이 남아 있는지
- `tests/test_task_store.py`: `current_task`의 날짜 판정(오늘 / 전날 끝남 / 자정 넘겨 진행 중)

## Verification (확인 방법)

1. `pip install -r requirements.txt -r requirements-dev.txt`
2. `pytest`로 전체 테스트, 단일 테스트는 `pytest tests/test_task_clock.py::test_name`
3. `python TaskPin.py`로 직접 확인
   - 트레이 메뉴에 "위젯 보이기"와 "종료"만 있는지
   - 위젯 우클릭 메뉴에 서버 관련 항목이 없는지
   - Task 등록 팝업에서 소요↔종료가 서로 계산되는지
   - 기본 시작시간이 15분 내림 값인지
   - 업무명이 투명도 위에 뜨고, 비우면 숨는지
   - 종료 시점에 트레이 알림이 한 번 뜨는지(소요를 가장 짧게 등록해서 확인)
   - 이름을 더블클릭해 편집하고 재시작 후에도 남아 있는지
   - TODO 추가, `(@` 리마인더, 완료 항목 정리 후 재시작 시 상태가 유지되는지
   - 정리된 항목이 `taskpin.db`의 `todos`에 `archived_at`과 함께 남아 있는지(sqlite3로 조회)
4. `%APPDATA%\TaskPin\`에 `config.json`과 `taskpin.db`만 생기고, 저장소나 실행 위치에는 파일이 생기지 않는지 확인
5. "윈도우 시작 시 실행"을 켠 뒤 `HKCU\...\Run\TaskPin` 값이 올바른지 확인
6. standalone 빌드로 확인한 뒤 onefile 빌드로 `Task알림.exe`를 실행해 3~5번을 다시 확인한다. 다른 폴더로 옮겨 실행해도 데이터가 그대로인지도 본다.

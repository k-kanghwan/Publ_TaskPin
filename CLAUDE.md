# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

- 현재 버전은 `version.py`의 `VERSION`(지금 0.1.12). 초기 구현 계획은 `.claude/plans/init-todo.md`, 요구사항 원본은 `PRD.md`이고, 기능 판단은 PRD를 따른다.
- 앱 표시명은 **Task알림**(창 제목·exe 표시명). 폴더명·자동 실행 레지스트리 키·단일 인스턴스 ID·mutex 같은 내부 식별자는 ASCII **TaskPin**을 쓴다.
- 앱 아이콘은 `ico/01_original_navy-coral/`의 `icon.svg`(트레이·창)와 `icon.ico`(exe/설치본)다. SVG를 고쳤을 때만 `python tools/make_ico.py`로 같은 폴더의 `icon.ico`를 다시 만든다. `img/image.png`는 참고 앱 화면이라 PRD의 FE 변경사항이 반영되지 않았다.
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
python tools/build_installer.py              # Nuitka 빌드 -> ISCC -> dist 확인까지 한 번에 (ISCC 경로 자동 탐색)
```

- 빌드 옵션은 `TaskPin.py` 맨 위 `# nuitka-project:` 주석에 있다. 버전은 루트 `version.py`의 `VERSION` 한 곳에서만 고친다(`--product-version`은 `nuitka-project-set`으로 이 파일을 읽는다). 설치본 버전은 exe에서 읽는다.
- **테스트는 항상 `.debug_appdata`에서만 한다.** 앱을 띄워 확인할 때(수동 테스트·스크린샷·`run` 스킬·동작 확인)는 반드시 `APPDATA=<repo>\.debug_appdata`, `TASKPIN_DEBUG=1`로 실행한다(`os_win.user_data_dir()`가 `APPDATA`를 따른다). 실제 `%APPDATA%\TaskPin`(config.json·taskpin.db)으로 앱을 띄우거나 그 파일을 읽고 쓰지 않는다. `.debug_appdata`는 `.gitignore`에 들어 있다.
  - `APPDATA`를 바꾸면 user site-packages(`%APPDATA%\Python`)도 함께 사라지므로 `PYTHONUSERBASE`를 원래 `%APPDATA%\Python`으로 지정한다(`anyio` 등 `pip --user` 패키지). `APPDATA`를 바꾸기 **전에** 지정해야 한다.

    ```powershell
    $env:PYTHONUSERBASE="$env:APPDATA\Python"; $env:APPDATA="$PWD\.debug_appdata"; $env:TASKPIN_DEBUG="1"; python TaskPin.py
    ```

  - `pytest`는 Qt 없이 `tmp_path`만 쓴다(`conftest.temp_db`, `monkeypatch.setattr(paths, "data_path", …)`). 새 테스트도 이 방식으로 써서 실제 데이터 경로를 건드리지 않게 한다.
- VS Code F5(`.vscode/launch.json`): "저장 시 재시작"은 `tools/dev_run.py`(watchfiles `run_process`)가 `.py` 저장마다 앱을 다시 띄운다. 두 구성 모두 위와 같은 환경변수(`APPDATA=.debug_appdata`, `PYTHONUSERBASE`, `TASKPIN_DEBUG=1`: 위젯 항상 위, 단일 인스턴스 ID 분리, 자동 실행 레지스트리 갱신·mutex 생략)로 실행한다.

## 구조

- `TaskPin.py` — `TaskPinApp(TrayApp)`: 위젯 연결, 1초 tick(현재시간·남은시간·Task 종료 트레이 알림 1회), Task 등록·수정·완료·해제
- `manager/` — Qt 없는 로직: `task_clock`(15분 단위·남은시간 계산), `task_store`/`todo_store`(SQLite), `todo_tree`(TODO 상위/하위), `todo_filter`(검색·날짜별 보기), `todo_export`(TODO → Markdown 체크리스트), `db`(연결 1개, `PRAGMA user_version` 마이그레이션), `widget_config`(config.json·단축키 기본값), `snippets`(`:트리거:` 치환), `paths`, `os_win`
- `ui/` — `clock_widget`(좌측 Task 패널 + TODO 배치, "멍청한 뷰"), `task_picker`(등록/수정 팝업), `confirm_dialog`(완료/해제 확인 창), `tag_dialog`(사용자 태그 추가), `color_dialog`(색 선택 창), `todo_panel`/`reminder_*`(참고 소스 이식), `settings_dialog`(설정창), `text_input`(이모지 패널 입력 보정·스니펫), `tray_app`, `theme`(런타임 테마: `current()`/`build()`)
- `tools/` — `dev_run`(F5 저장 시 재시작), `build_installer`(빌드부터 설치본까지 한 번에), `make_ico`(SVG → ico)

## 참고 소스: `C:\Users\kh.Cha\Documents\MyProject\Priv_WimsClockManager\`

이 프로젝트의 위젯/TODO 부분을 가져오고 사내 서버 연동은 뺐다(이식 완료). 아래는 이식 기준으로 남겨 둔다.

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
  - 버튼은 [등록/해제] [수정] [완료]. [등록/해제]는 Task가 없으면 "등록"(새 행), 진행 중이면 "해제"로 글자가 바뀐다. [수정]은 같은 행을 고치고(`task_store.update`, 종료를 미래로 바꾸면 종료 알림을 다시 받음), 등록 창(`TaskPicker(task)`)을 "Task 수정" 제목으로 띄운다.
  - 등록 창에서 업무명(선택)·상세 업무(선택, 여러 줄)·시작시간·소요 시간을 고른다. 시작시간은 15분 단위로 고르고, 등록 기본값은 현재시간을 15분 단위로 올린 값이다(06:36 → 06:45, `task_clock.ceil_slot`).
  - 완료/해제는 확인 창(`ui/confirm_dialog.py`, 시간이 남았으면 남은시간 표시)을 거친 뒤 기록을 남기고 위젯에서만 내린다: `tasks.cleared_at` + `tasks.cleared_as`(`task_store.COMPLETED` / `RELEASED`). 해제 확인은 경고색 버튼이다. v0.1.8까지 내린 행은 모두 completed로 옮겼다(스키마 v6).
  - 좌측 하단 배치: 상세 업무(비어 있으면 숨김) → 업무명 배지(가운데 정렬·테두리, 비어 있으면 숨김) → [등록/해제][수정][완료] → 투명도 슬라이더. 위젯 버튼은 `NoFocus`라 클릭해도 글자 둘레에 점선 포커스 표시가 생기지 않는다(`theme.button_style`도 `outline: none`). 상세 업무(`clock_widget._DetailLabel`)는 받은 높이에 들어가는 줄 수만큼 보여주고 넘치면 "…" + 툴팁이다. 가로 모드에서는 좌패널의 남는 높이를 모두 받아(stretch 1, 아래 정렬 - 여백 spacer는 stretch 0) 위젯을 키우면 더 많은 줄이 보이고, 세로 모드에서는 남는 높이를 TODO 목록이 받으므로 3줄까지만 요청한다(`TASK_DETAIL_MAX_LINES`). 상세 업무가 보이고 숨는 것이 바뀌면 `_apply_size_limits()`로 최소 높이를 다시 맞춘다.
  - 등록 창은 왼쪽이 업무명/시간 폼, 오른쪽이 상세 업무(`QPlainTextEdit`) 칸이다. 상세 칸에서 Enter는 줄바꿈이고 Ctrl+Enter는 어디서든 확인이다. 조합 중인 한글은 업무명처럼 preedit을 합쳐 읽는다.
  - 등록 창(`TaskPicker`)은 `Qt.Popup`이 아니라 활성화되는 Tool 창이다. Windows에서 Popup은 전경 창이 되지 않아 IME가 붙지 않는다(한글 입력 불가).
  - 등록 전에는 시작이 `--:--`. 종료 = 시작 + 소요 시간. 남은시간이 0을 지나면 초과 시간을 `+`로 표시한다.
- 더블클릭으로 편집할 수 있는 곳은 사용자 이름 하나뿐이다.
- 우클릭 메뉴는 패널마다 다르다. 좌패널(`ClockWidget.contextMenuEvent`): 가로/세로 모드·잠금·자동 실행·설정·위젯 숨기기·프로그램 종료. 우패널(`TodoPanel.contextMenuEvent`, 위로 올려 보내지 않음): 검색·완료 항목 정리·TODO 내보내기·추가·삭제·태그. 내보내기는 cfg(`export_dir`)가 필요해 `TodoPanel.export_requested`로 위젯에 맡긴다.
- 설정창(`ui/settings_dialog.py`)은 좌패널 우클릭 "설정"과 Ctrl+,로 연다(트레이 메뉴에는 넣지 않음). 탭은 Keyboard Shortcuts / Snippets / Appearance / Application이다. 확인 버튼 없이 바꾸는 즉시 저장한다.
  - 단축키(기본 E: [등록/해제] 버튼과 같음, R: 수정, C: 완료, A: 할 일 입력칸 포커스, Ctrl+F: 할 일 검색, Ctrl+,: 설정)는 `QShortcut(Qt.WindowShortcut)`이라 위젯 창이 활성일 때만 동작한다. 글자 키는 입력칸이 ShortcutOverride로 먼저 가져가므로 입력 중에는 글자로 들어간다. 새로 생긴 동작의 기본 키가 사용자가 이미 다른 동작에 쓰는 키면 비워 둔다(`widget_config.shortcuts`).
  - Appearance: 테마(다크/라이트/시스템), 강조색, 배경색, 폰트, 좌·우패널 글자 배율(`widget_config.LEFT_SCALES`/`TODO_SCALES`), TODO 글자색, 리마인더 알림 창 폭·글자 배율(`widget_config.POPUP_WIDTHS`/`POPUP_SCALES` → `theme.popup_width`/`popup_scale`), "글자도 함께 투명"(`fade_text`, 기본 끔: 투명도 슬라이더가 배경만 반투명하게 칠하고, 켜면 `setWindowOpacity`로 창 전체). 배경색을 고르면 글자색은 테마 대신 배경 밝기를 따른다. 단, 우클릭 메뉴 색(`theme.MENU_FIELDS`)은 배경색과 관계없이 테마 설정을 따른다(다크면 늘 어둡게). `theme.menu_style`을 위젯·설정창·등록 창 스타일시트에도 넣어 입력칸의 기본 우클릭 메뉴까지 같은 색으로 칠하고, 트레이 메뉴는 `TaskPinApp._apply_theme`이 칠한다. 알림 창 항목 아래에는 `ReminderPopup(preview=True)`를 실제 팝업과 같은 위젯 테마·폭·글자 크기로 넣고, Appearance 값이 바뀔 때마다 다시 만든다. 팝업 높이는 `adjustSize()`가 아니라 `heightForWidth(폭)`으로 정해 예시와 실제 크기가 같다. 설정창은 테마(다크/라이트)와 강조색만 따르고(`settings_dialog._settings_theme`), 제목줄도 `os_win.set_dark_title_bar(hwnd, dark)`로 맞춘다.
  - 테마 반영: `theme.build(appearance)` → `theme.set_current()` 후 `ClockWidget.apply_appearance()`(→ `TodoPanel.apply_appearance()`)로 다시 입힌다. 팝업은 만들 때 `theme.current()`를 읽는다. 스타일에 색을 쓸 때는 `ui.theme` 상수를 import하지 말고 `theme.current()`에서 읽고, 흰색 반투명은 `t.overlay(alpha)`로 쓴다(라이트에서는 검정).
  - Application: 설정 내보내기(폴더를 고르면 cfg를 `TaskPin-config-YYYYMMDD.json`으로 그대로 저장, `widget_config.export_config`) / 가져오기(`widget_config.read_import`가 알려진 키만 기본값 위에 덮어씀 → 확인 창 → `config_imported`). 가져오면 `TaskPinApp.apply_imported_config`가 위젯·설정창이 함께 쓰는 cfg dict를 **제자리에서** 바꾸고(`clear()` + `update()`) 테마·단축키·`ClockWidget.reload_config()`(방향·크기·위치·잠금·투명도·이름·표시)·`SettingsDialog.reload_values()`로 다시 적용한다. TODO/Task 기록(DB)은 들어가지 않는다.
  - 스니펫은 TODO 입력/수정칸과 Task 업무명에서 `:트리거:`를 치면 문구로 바꾼다. textEdited 안에서 바로 고치면 Ctrl+Z가 듣지 않으므로 `QTimer.singleShot(0)`으로 미뤄서 바꾼다.
- 이모지
  - Qt 6.8은 `WM_IME_CHAR`/`WM_CHAR`의 서로게이트 쌍을 버린다. 그래서 Win+. 이모지 패널로 고른 🚀 같은 이모지가 들어가지 않는다. `ui/text_input.ImeCharFilter`(앱 전체 네이티브 이벤트 필터)가 이 메시지를 대신 받아 IME 확정 문자열로 넣는다.
  - `QLineEdit` 위치는 UTF-16 단위다. 파이썬 문자열 index와 섞을 때는 `text_input.py_cursor()`/`utf16_pos()`를 쓴다.
  - 앱 폰트에 `PreferNoHinting`을 걸지 않는다. DirectWrite(Qt 6.8 기본)에서는 힌팅이 꺼져 한글이 흐려진다. 컬러 이모지는 TODO 행에서 14px로 키워 그린다(`todo_store.to_html(text, emoji_style)`).
- 이미 실행 중일 때 다시 실행하면 경고 없이 기존 앱의 위젯을 띄운다(`TrayApp.on_second_instance`). 기존 앱은 백그라운드라 전경 잠금에 걸리므로, 두 번째 실행이 `os_win.allow_set_foreground()`로 권한을 넘기고 연결이 끊길 때까지 기다린다.
- TODO 레벨: `todos.parent_id`(NULL이면 최상위)와 형제 사이 순서 `position`. 트리 규칙은 `manager/todo_tree.py`에 있다. 행 가운데에 놓으면 그 항목의 하위로, 행 위/아래 1/3에 놓으면 그 자리로 간다. "완료된 상위 ⇒ 하위도 모두 완료"를 유지하고, 상위를 삭제하면 하위는 한 단계 올린다. 들여쓰기는 3단계까지만 늘어난다.
- TODO 하위 접기: `todos.collapsed`(스키마 v7, 1이면 하위를 숨김). 행 맨 앞 ▸/▾ 버튼(`TodoRow.btn_toggle`, `TOGGLE_SIZE`)으로 바꾸고, 하위가 없으면 버튼을 숨기되 자리는 남겨 체크박스 위치를 맞춘다. 숨기는 일은 `todo_tree.flatten(hide_collapsed=)`가 하고, 검색·날짜별 보기로 거르는 중에는 접힘을 무시한다(맞는 항목이 접힌 상위 아래에 숨지 않게). 접힌 상위 아래로 추가하거나 끌어 놓으면 `todo_tree.expand_ancestors`로 펼친다. 숨은 하위는 선택에서 빠진다.
- TODO 선택: 클릭(그 행만)·Ctrl+클릭(추가/빼기)·Shift+클릭(범위), 빈 곳 클릭·Esc로 해제. 선택은 메모리에만 두고(`TodoPanel._selected`) 강조색 테두리로 그린다. 테두리는 행이 아니라 목록(container)의 Paint 이벤트에서 `_paint_selection`이 그리고, 화면에서 이어진 선택 행끼리는 둥근 사각형 하나로 묶는다(왼쪽 끝은 묶음에서 가장 얕은 레벨). 선택한 채 입력하면 마지막으로 클릭한 항목의 하위 맨 뒤로 들어간다. 선택한 행을 끌면 선택 항목이 함께 옮겨진다(`todo_tree.move_many`, 상위가 함께 선택된 항목은 상위를 따라감). 우클릭 "삭제"는 완료 없이 선택 항목을 지운다(하위는 한 단계 위로). 여러 개를 선택한 채 선택된 행에서 우클릭하면 선택이 유지되어 태그·삭제가 한꺼번에 적용된다(목록의 "빈 곳 클릭 → 선택 해제"는 왼쪽 버튼만 본다 - 행에서 올라온 우클릭 누름까지 지우면 안 됨). 선택 테두리 2px, 드래그 중 하위로 들어갈 행 테두리 2px·자리 표시선 3px.
- TODO 드래그는 `QDrag`(Windows OLE `DoDragDrop`)를 쓰지 않는다. OLE 루프 동안은 휠이 오지 않고 커서를 움직일 때만 자동 스크롤되기 때문이다. 행의 마우스 grab으로 이동/놓음을 받고(`TodoRow.drag_*` 시그널), 반투명 ToolTip 창이 커서를 따라가며, `QTimer`가 목록 위·아래 끝에서 계속 스크롤한다. 놓은 뒤 이동은 `QTimer.singleShot(0)`으로 미룬다(놓은 행이 rebuild로 사라짐).
- TODO 태그: `todos.tag`(기본 `todo_store.TAGS` 중 하나 / 사용자 태그 id `custom-xxxxxxxx` / NULL이면 없음). 기본 색은 `todo_panel.TAG_COLORS`, 사용자 태그는 config.json `custom_tags`(`widget_config.custom_tags()`가 깨진 항목을 거름). 태그 메뉴는 기본 6색 → 태그 없음 → 사용자 태그 → "+ 태그 추가…"(`TagDialog`, 이름+색) 순이고, 선택 항목들이 모두 같은 태그면 그 칸을 강조색 테두리로 감싼다(checkable·checked 액션 + `QMenu::item:checked`, 체크 표시는 숨김, "태그 없음"은 표시 안 함). 이름·색 변경과 삭제는 설정창 Appearance "TODO 태그"에서 한다. 사용자 태그를 지우면 그 태그를 붙인 할 일은 DB 값은 그대로 두고 태그 없음으로 보인다. 설정창은 cfg의 목록을 id로 고쳐 저장한다(그사이 위젯 메뉴에서 추가한 태그를 덮어쓰지 않게). 체크박스 왼쪽 세로 막대로만 표시하고(글자색·기울임 없음) 태그가 없어도 막대 자리는 비워 둔다.
- TODO 검색·날짜별 보기: 평소에는 숨어 있고 Ctrl+F·우패널 우클릭 "검색"으로 목록 위에 `FilterBar`([전체][오늘 n][지연 n][예정 n] 칩 + 검색칸)를 연다. 칩(`todo_panel._Chip`)은 스타일시트 `border-radius`가 안티앨리어싱 없이 그려져 끝이 깨지므로 QPainter로 직접 그린다. 규칙은 `manager/todo_filter.py`에 있다. 날짜별 보기는 미완료 리마인더만 `todo_store.due_at`(미룬 시각 우선) 기준으로 나눈다(지연: 지남 / 오늘: 오늘 안에 남음 / 예정: 내일 이후). 검색은 토큰을 뺀 본문에서 대소문자 없이, 공백으로 나눈 단어가 모두 들어 있어야 맞다. 맞는 항목의 상위는 흐리게(`TodoRow.context`) 함께 보인다. 검색어가 바뀔 때마다 맞는 글자(`todo_filter.match_spans`)만 노란 배경(`to_html(marks=…)`)으로 칠했다가 2초 뒤 서서히 지운다(`TodoPanel._mark_hold`/`_mark_fade`, 칩만 바꾸면 다시 시작하지 않음, 상위 문맥 행은 칠하지 않음). 검색칸은 조합 중인 한글까지 바로 거른다(`text_input.PreeditLineEdit`). 거르는 중에는 드래그하지 않고, 숨은 항목은 선택에서 빠지며, 할 일을 추가하면 전체 보기로 돌아간다. Esc는 검색어를 지우고, 비어 있으면 줄을 닫는다(닫으면 필터도 풀림). 필터 상태는 저장하지 않는다.

## 데이터 저장 / 경로

- 사용자 데이터 위치: `%APPDATA%\TaskPin\`
  - `config.json` — 위젯 설정(위치·크기·투명도·모드 등), 사용자 이름, `shortcuts`(동작별 QKeySequence PortableText), `snippets`(`[[":idea:", "💡"], ...]`), `appearance`(`widget_config.appearance()`가 깨진 값을 기본값으로 채움), `export_dir`(TODO·설정 내보내기 마지막 폴더), `custom_tags`(사용자 TODO 태그). 크기는 세로 모드 `vertical_width`·`height`, 가로 모드 `width`·`horizontal_height`를 따로 저장한다. 세로 모드는 폭 280~364(1.3배)·높이 최소~583(486의 1.2배), 가로 모드는 폭 540~810·높이 최소~1.5배. 높이는 하단 핸들, 폭은 우측 핸들로 조절하고, 좌측 칼럼은 가로 모드에서만 폭이 고정이다
  - `taskpin.db` — SQLite: TODO(계층·태그·접힘 포함), 정리된 완료 항목, Task 등록 정보(업무명·상세 업무·시간·완료/해제)
- "완료 항목 정리"(`TodoPanel.clear_done`)는 행을 지우지 않고 보관 상태로 바꾼다.
- "TODO 내보내기"(우패널 우클릭 서브메뉴: 화면 목록 / 보관 항목 전체)는 Markdown 체크리스트(.md, UTF-8)로 저장한다. 하위는 2칸 들여쓰기, 보관 항목은 보관 날짜별 섹션. 보관 항목은 섹션마다 상위 사슬을 함께 쓴다(`todo_export._with_ancestors`) - 상위가 화면 목록에 남아 있으면(미완료) `- [ ]`로, 다른 날짜에 보관됐으면 그 섹션에도 다시 나온다. 그래야 하위가 다른 항목의 하위나 최상위처럼 보이지 않는다. 텍스트를 그대로 써서 `(@...)` 리마인더 토큰이 Obsidian에서도 읽힌다.
- 참고 소스처럼 `os.chdir(BASE_DIR)` 후 CWD 기준 `src/*`에 쓰면 안 된다. 자동 실행 시 CWD는 system32이고, 설치 폴더(`%LOCALAPPDATA%\Programs\TaskPin`)는 재설치·제거 때 바뀐다.
- 번들 리소스(아이콘 등)는 `paths.resource_path()`(`__file__` 기준)로 찾는다. 컴파일 여부는 `"__compiled__" in globals()`, exe 경로는 `sys.argv[0]` 기준. PyInstaller의 `sys._MEIPASS`는 쓰지 않는다.

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

## Git

- commit에 claude의 서명은 절대 넣지 않음

## Versioning

- Sementic 버저닝을 채택
- 기능이 추가될 때마다 세번째 자리를 올린다.
- 두번째 자리는 사용자가 요청할 때만 올린다.
- 첫번째 자리는 사용자가 요청할 때만 올린다.

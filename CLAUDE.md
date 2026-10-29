# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

- 현재 버전은 `version.py`의 `VERSION`(지금 0.1.25). 초기 구현 계획은 `.claude/plans/init-todo.md`, 요구사항 원본은 `PRD.md`이고, 기능 판단은 PRD를 따른다.
- 앱 표시명은 **Task알림**(창 제목·exe 표시명). 폴더명·자동 실행 레지스트리 키·단일 인스턴스 ID·mutex 같은 내부 식별자는 ASCII **TaskPin**을 쓴다.
- 앱 아이콘은 `ico/01_original_navy-coral/`의 `icon.svg`(트레이·창)와 `icon.ico`(exe/설치본)다. 트레이·창 아이콘은 설정 Application "앱 아이콘"(cfg `app_icon`: `dark`=01 navy-coral / `light`=`ico/03_light-indigo/icon.svg`, `TaskPin.APP_ICONS` → `TaskPinApp._apply_app_icon` → `TrayApp.set_icon`)으로 바로 바꾼다. exe·바로가기 아이콘은 빌드 때 박히므로 늘 01이다. 디버그 실행(`TASKPIN_DEBUG=1`)은 설정과 관계없이 트레이·창 아이콘을 `ico/02_graphite-lime/icon.svg`로 바꿔 설치본과 구별한다(`TaskPinApp.TRAY_ICON`, 빌드에는 넣지 않음). SVG를 고쳤을 때만 `python tools/make_ico.py`로 같은 폴더의 `icon.ico`를 다시 만든다. `img/image.png`는 참고 앱 화면이라 PRD의 FE 변경사항이 반영되지 않았다.
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
- `manager/` — Qt 없는 로직: `task_clock`(15분 단위·남은시간 계산), `task_store`/`todo_store`(SQLite), `todo_tree`(TODO 상위/하위·삭제 자리 되돌리기), `todo_trash`(지운 TODO 이력), `todo_pages`(TODO 페이지), `todo_filter`(검색·날짜별 보기), `todo_export`(TODO → Markdown 체크리스트), `db`(연결 1개, `PRAGMA user_version` 마이그레이션), `widget_config`(config.json·단축키 기본값), `snippets`(`:트리거:` 치환), `paths`, `os_win`
- `ui/` — `clock_widget`(좌측 Task 패널 + TODO 배치, "멍청한 뷰"), `task_picker`(등록/수정 팝업), `confirm_dialog`(완료/해제·삭제·초기화 확인 창, 문구 입력 확인), `tag_dialog`(사용자 태그 추가·페이지 이름), `page_bar`(TODO 페이지 이름 칩·점), `color_dialog`(색 선택 창), `todo_panel`/`reminder_*`(참고 소스 이식), `settings_dialog`(설정창), `text_input`(이모지 패널 입력 보정·스니펫·Enter를 먼저 받는 `LineEdit`), `painted`(직접 그리는 체크박스·이름 테두리·알람 시계 아이콘), `tray_app`, `theme`(런타임 테마: `current()`/`build()`)
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
  - 등록 창에서 업무명(필수)·상세 업무(선택, 여러 줄)·시작시간·소요 시간을 고른다. 업무명이 비면 확인 버튼이 꺼지고, Enter를 누르면 업무명 칸을 경고 테두리(`property("invalid")`)로 표시한다. 시작시간은 15분 단위로 고르고, 등록 기본값은 현재시간을 15분 단위로 올린 값이다(06:36 → 06:45, `task_clock.ceil_slot`).
  - 완료/해제는 확인 창(`ui/confirm_dialog.py`, 시간이 남았으면 남은시간 표시)을 거친 뒤 기록을 남기고 위젯에서만 내린다: `tasks.cleared_at` + `tasks.cleared_as`(`task_store.COMPLETED` / `RELEASED`). 해제 확인은 경고색 버튼이다. v0.1.8까지 내린 행은 모두 completed로 옮겼다(스키마 v6).
  - 좌측 하단 배치: 상세 업무(비어 있으면 숨김) → 업무명 배지(가운데 정렬·테두리, 비어 있으면 숨김) → [등록/해제][수정][완료]. 투명도는 설정창 Appearance 슬라이더로 옮겼다(좌패널에는 없음). 위젯 버튼은 `NoFocus`라 클릭해도 글자 둘레에 점선 포커스 표시가 생기지 않는다(`theme.button_style`도 `outline: none`). 상세 업무(`clock_widget._DetailLabel`)는 받은 높이에 들어가는 줄 수만큼 보여주고 넘치면 "…" + 툴팁이다. 가로 모드에서는 좌패널의 남는 높이를 모두 받아(stretch 1, 아래 정렬 - 여백 spacer는 stretch 0) 위젯을 키우면 더 많은 줄이 보이고, 세로 모드에서는 남는 높이를 TODO 목록이 받으므로 3줄까지만 요청한다(`TASK_DETAIL_MAX_LINES`). 상세 업무가 보이고 숨는 것이 바뀌면 `_apply_size_limits()`로 최소 높이를 다시 맞춘다.
  - 등록 창은 왼쪽이 업무명/시간 폼, 오른쪽이 상세 업무(`QPlainTextEdit`) 칸이다. 상세 칸에서 Enter는 줄바꿈이고 Ctrl+Enter는 어디서든 확인이다. 조합 중인 한글은 업무명처럼 preedit을 합쳐 읽는다.
  - 등록 창(`TaskPicker`)은 `Qt.Popup`이 아니라 활성화되는 Tool 창이다. Windows에서 Popup은 전경 창이 되지 않아 IME가 붙지 않는다(한글 입력 불가). 등록 창도 수정 창과 같은 자리([수정] 버튼 위, `popup_for(btn_task_edit)`)에 띄운다.
  - 등록/수정 창은 다른 창을 눌러 포커스가 옮겨져도 닫지 않는다(취소·Esc·확인으로만 닫힘). 한 번에 하나만 띄우고(`TaskPinApp._picker`, 이미 떠 있으면 앞으로), Task를 완료/해제하면 열린 수정 창은 닫는다. 위젯을 끌어 옮기면 열린 창도 같은 만큼 따라간다(`TaskPicker`가 위젯 창의 Move 이벤트를 받음, 사용자가 옮겨 둔 자리도 위젯 기준으로 유지). 등록 창을 확인 없이 닫으면 적던 업무명·상세 업무를 `TaskPinApp._task_draft`에 남겨(앱 실행 중에만, config에 넣지 않음) 다음 [등록] 때 `TaskPicker(draft=)`로 채운다. 시작·소요는 늘 새 기본값이다.
  - 등록/수정 창이 떠 있는 동안 위젯은 투명한 막(`clock_widget._InputBlocker`, `ClockWidget.set_input_blocked`)이 덮는다. 누름·이동·뗌은 부모로 넘겨 창 이동만 되고, 항목 클릭·우클릭·휠·키·창 단축키(ShortcutOverride를 막이 받음)·크기 조절은 막는다. 막을 눌렀다 떼면 `blocked_clicked` → `TaskPinApp._raise_picker`로 등록 창을 다시 앞으로 올린다. 막을 걷을 때 포커스는 목록으로 먼저 돌린다.
  - 등록 전에는 시작이 `--:--`. 종료 = 시작 + 소요 시간. 남은시간이 0을 지나면 초과 시간을 `+`로 표시한다.
- 좌패널에서 더블클릭으로 편집할 수 있는 곳은 사용자 이름 하나뿐이다. 사용자 이름은 테두리(`ui/painted.EditableLabel`, 편집칸과 같은 두께·여백, hover 때 진하게)로 표시하고, 테두리가 글자만 감싸도록 레이아웃에 왼쪽 정렬로 넣는다. TODO 페이지 이름은 페이지 칩(`page_bar.PageTabs`)을 더블클릭해 바꾼다.
- 우클릭 메뉴는 패널마다 다르다. 좌패널(`ClockWidget.contextMenuEvent`): 가로/세로 모드·잠금·자동 실행·설정·위젯 숨기기·프로그램 종료. 우패널(`TodoPanel.contextMenuEvent`, 위로 올려 보내지 않음): 연관된 것끼리 구분선으로 묶는다 - [검색·페이지로 이동] / [모두 접기·모두 펼치기] / [추가·아래에 구분선 추가·삭제·삭제 이력] / [잘라내기·복사·붙여넣기] / [태그] / [완료 항목 정리·내보내기]. 메뉴 키·Shift+F10(키보드 메뉴 이벤트)은 커서 자리(목록 가운데라 엉뚱한 행)가 아니라 지금 행 바로 아래에서 연다(`TodoPanel.show_current_menu`, 포커스 위젯이 없을 때는 `ClockWidget.contextMenuEvent`가 넘김). 내보내기는 cfg(`export_dir`)가 필요해 `TodoPanel.export_requested`로 위젯에 맡긴다.
- 설정창(`ui/settings_dialog.py`)은 좌패널 우클릭 "설정"과 Ctrl+,로 연다(트레이 메뉴에는 넣지 않음). 탭은 Keyboard Shortcuts / Snippets / Appearance / Application이다(행이 많아 모두 스크롤, `_group_page`). 확인 버튼 없이 바꾸는 즉시 저장한다. 마지막으로 본 탭은 앱이 실행되는 동안만 기억해(`SettingsDialog._last_tab`, 저장하지 않음) 다시 열면 그 탭부터 보여준다.
  - 단축키(기본 E: [등록/해제] 버튼과 같음, R: 수정, C: 완료, A: 할 일 입력칸 포커스, Enter: 선택한 할 일 수정, Ctrl+F: 할 일 검색, Ctrl+PgUp/Ctrl+PgDown: 이전/다음 페이지, Ctrl+,: 설정)는 `QShortcut(Qt.WindowShortcut)`이라 위젯 창이 활성일 때만 동작한다. 할 일 수정은 F2가 고정 키로 늘 된다(`clock_widget.FIXED_EDIT_KEY`, 선택이 없으면 F2만 페이지 이름 바꾸기 - Enter로는 이름 창이 뜨지 않음). 다른 동작이 F2로 시작하면 같은 키의 단축키가 둘이 되어 둘 다 듣지 않으므로 고정 F2를 걸지 않는다. 기본값을 F2에서 Enter로 바꿨지만 이미 저장된 값은 그대로 둔다. 단축키 행의 설명은 줄바꿈한다 - 길면 줄이 넓어져 키 입력칸·↺가 오른쪽으로 밀려 잘린다. 목록 키(< / >: 선택한 할 일 단계 올리기·내리기(`TodoPanel.shift_level` - 내리기는 화면에서 바로 위 형제의 하위 맨 뒤로(`todo_tree.indent_target`, 위 형제가 없거나 구분선이면 그대로), 올리기는 상위 바로 뒤 형제로(`todo_tree.outdent_target`, 최상위면 그대로), 하위는 따라가고 이어진 형제는 순서를 지킨다, 거르는 중에는 안 함). Shift로 치는 기호 키는 Shift를 떼고 비교한다(`todo_panel.plain_symbol` - 설정에 "<"로 두어도 "Shift+<"로 저장돼도 같은 키, 설정창 겹침 검사도 같음, 글자 키 Shift+G는 그대로), Space: 선택한 할 일 완료/해제 - 하나라도 미완료면 모두 완료, 모두 완료면 모두 해제(`TodoPanel.toggle_selected`), Del / Ctrl+X / Ctrl+C / Ctrl+V: 삭제·잘라내기·복사·붙여넣기, ↑/↓/←/→: 할 일 위·아래 선택·하위 접기·펼치기, G, G / Shift+G: 맨 위·맨 아래 - vim의 gg/G, `widget_config.LIST_SHORTCUTS`)도 같은 탭에서 바꾸지만 창 단축키로 걸지 않고 `TodoPanel.set_nav_keys`로 넘긴다 - 입력칸의 화살표를 가로채지 않게 목록에 포커스가 있을 때(또는 포커스 위젯이 없을 때)만 듣는다. 단축키는 두 키까지 이어 누를 수 있다(`_ShortcutEdit` 최대 2키, "G, G"). 목록 키의 두 키는 `TodoPanel._nav_action`이 첫 키를 받아 두고 1초(`NAV_SEQUENCE_MS`) 안에 다음 키를 기다린다(창 단축키는 QShortcut이 처리). 겹침 검사는 같은 키뿐 아니라 앞부분이 같은 키("G"와 "G, G")도 막는다(`settings_dialog._keys_overlap`). 단축키 탭은 그룹(Task 관리 / 편집 / 탐색 / 페이지 / 일반, `SHORTCUT_GROUPS`)으로 나누고 Appearance처럼 스크롤된다(`SettingsDialog._group_page`). 글자 키는 입력칸이 ShortcutOverride로 먼저 가져가므로 입력 중에는 글자로 들어간다. Enter는 QLineEdit이 먼저 가져가지 않으므로 위젯의 입력칸은 `text_input.LineEdit`(조합 키 없는 Enter의 ShortcutOverride를 받음)을 쓴다 - 할 일 수정 단축키를 Enter로 바꿔도 할 일 추가·수정·이름 입력이 Enter로 끝난다. 새로 생긴 동작의 기본 키가 사용자가 이미 다른 동작에 쓰는 키면 비워 둔다(`widget_config.shortcuts`).
  - Appearance: 테마(다크/라이트/시스템), 강조색, 배경색, 투명도(슬라이더 0~80%, cfg `opacity`에 불투명도로 저장 - `widget_config.opacity`/`set_transparency`, 끄는 중에는 `opacity_changed`로 위젯에만 반영하고 놓을 때 저장. 슬라이더 `min-height`는 화면 배율이 클수록 기본 높이가 줄어 핸들이 잘리지 않게), 폰트, 좌·우패널 글자 배율(`widget_config.LEFT_SCALES`/`TODO_SCALES`), TODO 글자색, 완료 항목 취소선(`todo_strike`, 기본 켬), 행 구분선(`todo_row_lines`, 기본 끔), 하위 가이드 선(`todo_guides`, 기본 켬), 페이지 표시 위치(`page_bar`: 위/아래/왼쪽/오른쪽), 리마인더 알림 창 폭·글자 배율(`widget_config.POPUP_WIDTHS`/`POPUP_SCALES` → `theme.popup_width`/`popup_scale`, 글자 배율은 창 폭·여백·아이콘에도 곱한다 - 실제 폭 = `px(popup_width, popup_scale)`, 설정창은 가장 큰 예시(494px)가 잘리지 않게 폭 800), "글자도 함께 투명"(`fade_text`, 기본 끔: 투명도 슬라이더가 배경만 반투명하게 칠하고, 켜면 `setWindowOpacity`로 창 전체). 배경색을 고르면 글자색은 테마 대신 배경 밝기를 따른다. 단, 우클릭 메뉴 색(`theme.MENU_FIELDS`)은 배경색과 관계없이 테마 설정을 따른다(다크면 늘 어둡게). `theme.menu_style`을 위젯·설정창·등록 창 스타일시트에도 넣어 입력칸의 기본 우클릭 메뉴까지 같은 색으로 칠하고, 트레이 메뉴는 `TaskPinApp._apply_theme`이 칠한다. 알림 창 항목 아래에는 `ReminderPopup(preview=True)`를 실제 팝업과 같은 위젯 테마·폭·글자 크기로 넣고, Appearance 값이 바뀔 때마다 다시 만든다. 팝업 높이는 `adjustSize()`가 아니라 `heightForWidth(폭)`으로 정해 예시와 실제 크기가 같다. 설정창은 테마(다크/라이트)와 강조색만 따르고(`settings_dialog._settings_theme`), 제목줄도 `os_win.set_dark_title_bar(hwnd, dark)`로 맞춘다.
  - 테마 반영: `theme.build(appearance)` → `theme.set_current()` 후 `ClockWidget.apply_appearance()`(→ `TodoPanel.apply_appearance()`)로 다시 입힌다. 팝업은 만들 때 `theme.current()`를 읽는다. 스타일에 색을 쓸 때는 `ui.theme` 상수를 import하지 말고 `theme.current()`에서 읽고, 흰색 반투명은 `t.overlay(alpha)`로 쓴다(라이트에서는 검정).
  - Application: "앱" 그룹(앱 아이콘 다크/라이트 `app_icon` = `widget_config.APP_ICONS`, 바꾸면 `app_icon_changed`), "TODO" 그룹(할 일 삭제 확인 `confirm_delete`, 되돌릴 수 있는 삭제 수 `undo_limit` = `widget_config.UNDO_LIMITS`), "설정 파일" 그룹, "데이터" 그룹(모든 데이터 초기화). 설정 내보내기(폴더를 고르면 cfg를 `TaskPin-config-YYYYMMDD.json`으로 그대로 저장, `widget_config.export_config`) / 가져오기(`widget_config.read_import`가 알려진 키만 기본값 위에 덮어씀 → 확인 창 → `config_imported`). 가져오면 `TaskPinApp.apply_imported_config`가 위젯·설정창이 함께 쓰는 cfg dict를 **제자리에서** 바꾸고(`clear()` + `update()`) 테마·단축키·`ClockWidget.reload_config()`(방향·크기·위치·잠금·투명도·이름·표시)·`SettingsDialog.reload_values()`로 다시 적용한다. TODO/Task 기록(DB)은 들어가지 않는다.
  - 모든 데이터 초기화: git 저장소 삭제처럼 문구(`settings_dialog.RESET_PHRASE` "모든 데이터 초기화")를 똑같이 입력해야 확인 버튼이 켜진다(`ConfirmDialog(confirm_phrase=)`, 조합 중인 한글 포함). `db.reset_all`이 먼저 `%APPDATA%\TaskPin\taskpin-backup-YYYYMMDD-HHMMSS.db`로 백업(sqlite backup)하고, 백업하지 못하면 지우지 않는다. 그다음 todos·tasks·todo_deletions·todo_pages를 비우고 번호(`sqlite_sequence`)를 처음부터, "페이지 1"을 다시 만들고 VACUUM 한다. 백업을 남긴다는 말은 사용자에게 하지 않는다. 설정(config.json)은 그대로다. 비운 뒤 `data_reset` → `TaskPinApp.reload_data`가 메모리의 Task·임시저장·등록 창·리마인더 팝업을 정리하고 `TodoPanel.reload()`로 다시 읽는다(메모리 목록을 그대로 두면 다음 저장이 지운 행을 되살린다).
  - 스니펫은 TODO 입력/수정칸과 Task 업무명에서 `:트리거:`를 치면 문구로 바꾼다. textEdited 안에서 바로 고치면 Ctrl+Z가 듣지 않으므로 `QTimer.singleShot(0)`으로 미뤄서 바꾼다.
- 둥근 테두리: Qt 스타일시트의 `border-radius`는 125%·150% 배율에서 모서리가 계단처럼 깨지므로 둥근 배경·테두리는 모두 `ui/painted`가 QPainter(`Antialiasing`)로 그린다. 스타일시트는 글자·여백과 **같은 두께의 투명 테두리**(`border: 1px solid transparent`, 배경 `transparent`)만 정한다.
  - 버튼·입력칸·카드: 창/패널마다 `painted.set_boxes(root, [(클래스, objectName|None, Box|None), ...])`로 규칙을 건다(가장 가까운 상위의 규칙, 위에서부터 처음 맞는 것; `None`은 그리지 않음 - 목록의 접기·✕ 같은 작은 버튼). 앱 필터가 새 위젯의 Polish·ParentChange 때 규칙을 찾아 붙이므로 나중에 만든 행도 따른다(부모 없이 크기를 잰 뒤 레이아웃에 넣는 위젯은 Polish 때 규칙을 못 찾음). ParentChange는 그 위젯과 자식 중 이미 Polish 된 것만 본다 - 부모를 주고 만드는 위젯(목록 행 등)은 곧 Polish 때 찾으므로, 모두 보면 행을 만들 때 느려진다. 부모 없이 만든 설정창 행처럼 위젯은 Polish 전이어도 자식(키 입력칸 등)은 Polish 됐을 수 있으므로 자식도 본다. 위젯 하나는 `set_box`(배지·상태 점·색 칸·드롭 표시). 테마를 바꾸면 스타일시트와 함께 다시 부른다.
  - `Box` 상태: 사용 불가(off_*) / 누름·마우스 올림 → 체크 → 포커스 → `property("invalid")`(설정창 입력 오류). 모양은 `painted.button_box`(theme.button_style 버튼)·`accent_box`(확인 버튼)·`input_box`·`form_rules`(theme.popup_form_style 입력칸).
  - 체크박스(`painted.CheckBox`, 체크하면 ✓)와 이름 테두리(`EditableLabel`), 검색 칩(`todo_panel._Chip`), 페이지 칩(`page_bar.PageTabs`), 접기 꺾쇠(`todo_panel._ToggleButton`), 설정창 되돌리기 버튼(`settings_dialog._ResetButton`, ↶ 굽은 화살표 - ↺ 글자는 글꼴에 따라 깨짐)은 위젯이 직접 그린다. 슬라이더·스크롤바·메뉴는 아직 스타일시트다.
  - 리마인더 알람 시계(할 일 행의 시각 앞·알림 팝업 제목 앞)는 ⏰ 이모지 대신 `painted.alarm_pixmap`(시계판·바늘·종·다리를 한 색 선으로)으로 그린다. 색은 강조색(행: 지났으면 경고색, 완료면 흐리게). RichText 라벨에는 `painted.alarm_img`(data URI `<img>`, 화면 배율 픽셀로 그려 캐시)로 넣는다 - 크게 그려 줄이면 QTextDocument가 매끄럽게 줄이지 않아 깨진다. 트레이 풍선 제목(OS가 그림)만 ⏰ 글자다.
- 이모지
  - Qt 6.8은 `WM_IME_CHAR`/`WM_CHAR`의 서로게이트 쌍을 버린다. 그래서 Win+. 이모지 패널로 고른 🚀 같은 이모지가 들어가지 않는다. `ui/text_input.ImeCharFilter`(앱 전체 네이티브 이벤트 필터)가 이 메시지를 대신 받아 IME 확정 문자열로 넣는다.
  - `QLineEdit` 위치는 UTF-16 단위다. 파이썬 문자열 index와 섞을 때는 `text_input.py_cursor()`/`utf16_pos()`를 쓴다.
  - 앱 폰트에 `PreferNoHinting`을 걸지 않는다. DirectWrite(Qt 6.8 기본)에서는 힌팅이 꺼져 한글이 흐려진다. 컬러 이모지는 TODO 행에서 14px로 키워 그린다(`todo_store.to_html(text, emoji_style)`).
- 이미 실행 중일 때 다시 실행하면 경고 없이 기존 앱의 위젯을 띄운다(`TrayApp.on_second_instance`). 기존 앱은 백그라운드라 전경 잠금에 걸리므로, 두 번째 실행이 `os_win.allow_set_foreground()`로 권한을 넘기고 연결이 끊길 때까지 기다린다.
- TODO 레벨: `todos.parent_id`(NULL이면 최상위)와 형제 사이 순서 `position`. 트리 규칙은 `manager/todo_tree.py`에 있다. 행 가운데에 놓으면 그 항목의 하위로, 행 위/아래 1/3에 놓으면 그 자리로 간다. "완료된 상위 ⇒ 하위도 모두 완료"를 유지하고(해제하면 상위와 하위를 모두 해제), 상위를 삭제하면 하위는 한 단계 올린다. 들여쓰기는 레벨 수 제한 없이 `INDENT_STEP`씩 늘어난다(좁은 세로 모드에서 아주 깊으면 글자 폭이 줄어듦).
- TODO 하위 접기: `todos.collapsed`(스키마 v7, 1이면 하위를 숨김). 행 맨 앞 꺾쇠 버튼(`TodoRow.btn_toggle` = `_ToggleButton`, 접힘 › / 펼침 ⌄, `TOGGLE_SIZE`)으로 바꾸고 - ▸/▾·▶/▼ 글자는 글꼴에 따라 이모지로 바뀌거나 깨지므로 직접 그린다 - 하위가 없으면 버튼을 숨기되 자리는 남겨 체크박스 위치를 맞춘다. 숨기는 일은 `todo_tree.flatten(hide_collapsed=)`가 하고, 검색·날짜별 보기로 거르는 중에는 접힘을 무시한다(맞는 항목이 접힌 상위 아래에 숨지 않게). 접힌 상위 아래로 추가하거나 끌어 놓으면 `todo_tree.expand_ancestors`로 펼친다. 숨은 하위는 선택에서 빠진다. 우클릭 "모두 접기/펼치기"는 `todo_tree.set_all_collapsed`(하위가 있는 항목만)를 쓰고 지금 행을 화면에 남긴다. 하나를 펼치면(꺾쇠·→) 펼친 하위의 마지막 행까지 보이게 스크롤하고, 하위가 화면보다 길면 상위를 맨 위에 둔다(`TodoPanel._reveal_subtree`).
- TODO 목록 그림(`TodoPanel._paint_list`, container의 Paint 이벤트라 행보다 먼저 = 행 아래에 깔림): 행 구분선(설정) → 하위 레벨 가이드 선(설정 `todo_guides`) → 선택 테두리. 가이드 선은 상위의 접기 꺾쇠 가운데에서 내려오는 강조색 1px 세로선(`GUIDE_ALPHA`)이고, 행마다 위 간격부터 아래 끝까지 그어 이어진 하위끼리 한 줄이 된다. 행의 수정 입력칸(`TodoRow.editor`)은 처음 수정할 때 만들고, 글자 더블클릭은 라벨이 마우스를 받지 않아 행의 `mouseDoubleClickEvent`로 받는다(행마다 입력칸·이벤트 필터를 두면 목록을 펼칠 때 느려짐).
- TODO 선택: 클릭(그 행만)·Ctrl+클릭(추가/빼기)·Shift+클릭(범위), 빈 곳 클릭·Esc로 해제. 선택은 메모리에만 두고(`TodoPanel._selected`) 강조색 테두리로 그린다. 테두리는 행이 아니라 목록(container)의 Paint 이벤트에서 `_paint_selection`이 그리고, 화면에서 이어진 선택 행끼리는 둥근 사각형 하나로 묶는다(왼쪽 끝은 묶음에서 가장 얕은 레벨). 선택한 채 입력하면 마지막으로 클릭한 항목의 하위 맨 뒤로 들어간다(구분선을 골랐으면 그 바로 아래 형제로). 선택한 행을 끌면 선택 항목이 함께 옮겨진다(`todo_tree.move_many`, 상위가 함께 선택된 항목은 상위를 따라감). Ctrl을 누른 채 놓으면 복사(`_copy_items`, 끄는 그림에 + 배지 - Ctrl을 누르고 떼면 바로 바뀜, 놓을 때 `QGuiApplication.queryKeyboardModifiers`), Shift·그냥은 이동이다. 우클릭 "삭제"는 완료 없이 선택 항목을 지운다(하위는 한 단계 위로). 여러 개를 선택한 채 선택된 행에서 우클릭하면 선택이 유지되어 태그·삭제가 한꺼번에 적용된다(목록의 "빈 곳 클릭 → 선택 해제"는 왼쪽 버튼만 본다 - 행에서 올라온 우클릭 누름까지 지우면 안 됨). 선택 테두리 2px, 드래그 중 하위로 들어갈 행 테두리 2px·자리 표시선 3px.
- TODO 목록 다시 그리기(`TodoPanel._rebuild`)는 있던 항목의 행을 id로 다시 쓰고(`TodoRow.set_state`) 새 항목만 행을 만든다. 체크·접기마다 행을 모두 새로 만들면 150개에서 한 번에 0.3초 넘게 걸린다.
  - 행은 항목 id → 행(`TodoPanel._row_cache`)으로 기억한다. 다른 페이지·접힘·거름으로 안 보이게 된 행은 지우지 않고 숨겨 레이아웃에서만 뺀다(`_stash_row`). 지워지거나 보관된 항목의 행만 지운다(`_drop_row`). 페이지를 넘길 때마다 행을 새로 만들면 70개 페이지에서 한 번에 0.3초가 걸렸다(다시 쓰면 0.06초).
  - 시작하고 1.5초 뒤부터 쉬는 동안 아직 행이 없는 항목(다른 페이지·접힌 하위)의 행을 8개씩 미리 만들어 polish까지 해 둔다(`_warm_rows`) - 페이지를 처음 넘길 때도 빠르게.
  - 새 행은 `parent=container`로 만들어 넣자마자 `show()`한다. 레이아웃의 지연 표시를 기다리면 그 사이 목록 높이가 줄어 스크롤이 맨 위로 잘린다.
  - 행 안의 자식 위젯도 모두 행을 부모로 만든다. 부모 없이 `setVisible(True)` 하면 레이아웃에 들어가기 전까지 최상위 창으로 떠서 화면 가운데가 깜빡인다.
  - 막 다시 그린 목록에서 행을 보이게 할 때는 `_reveal(row)`를 쓴다(레이아웃을 바로 끝낸 뒤 `ensureWidgetVisible`). 그냥 `ensureWidgetVisible`을 부르면 스크롤 범위가 아직 옛 크기라 맨 아래 행이 잘린다.
  - 행의 체크박스·✕는 `NoFocus`다. 수정을 끝내거나 행을 지울 때는 포커스를 목록(`container`)으로 먼저 돌린다. 포커스를 가진 위젯을 숨기면 Qt가 다음 위젯으로 포커스를 넘기며 목록을 스크롤한다.
- TODO 키보드 이동(`TodoPanel.handle_nav_key`): 설정 단축키(기본 ↑↓←→·gg·Shift+G·Del·Ctrl+X/C/V, 조합 키·두 키도 가능) - 위/아래 행 선택(선택이 없으면 이 페이지에서 마지막으로 골랐던 행(`_last_ids`, 실행 중에만)부터, 그 행이 안 보이면 보이는 영역 가운데 행부터), 맨 위/맨 아래, 접기(펼친 상위면 접고 아니면 상위로), 펼치기(접힌 상위면 펴고 펼쳤으면 첫 하위로; 검색·날짜별 보기 중에는 접힘을 무시하므로 이동만), 삭제·잘라내기·복사·붙여넣기. 고정 키(`todo_panel.FIXED_NAV_KEYS`, 설정 키를 바꿔도 함께 동작): ↑/↓ 위·아래, ←/→ 접기·펼치기, Home/End 처음/마지막, Delete 선택 항목 삭제(우클릭 "삭제"와 같이 확인 창, 지운 뒤 그 자리의 행을 골라 이어서 지울 수 있음), Ctrl+X/C/V. 목록(`container`)의 eventFilter가 이 키를 먼저 가져가 스크롤 영역의 화살표 스크롤을 막는다(PgUp/PgDn·휠은 그대로). 스크롤 영역과 스크롤바는 `NoFocus`라 스크롤바를 끈 뒤에도 ↑↓가 스크롤이 아니라 선택으로 간다.
  - 입력칸·검색칸에서 Esc로 빠지면 `clearFocus()`가 아니라 목록으로 포커스를 옮겨 바로 ↑↓가 듣는다. 목록 포커스는 글자 단축키(E/C/A)를 막지 않는다. 포커스 위젯이 없을 때(좌패널 클릭 뒤 등)는 `ClockWidget.keyPressEvent`가 목록으로 넘긴다. 입력칸·행 편집칸 안의 ↑↓는 목록으로 새지 않는다.
  - 할 일 수정(고정 F2 + 설정 단축키 `todo_edit`, 기본 Enter)은 지금 행(`_current_row`: 마지막으로 고른 행)을 그 자리에서 수정한다(`edit_current`). 수정을 끝내면 포커스가 목록으로 돌아와 이어서 ↑↓로 움직인다. 고른 행이 없으면 F2만 지금 페이지 이름 바꾸기(`edit_current(rename_page=True)` → `rename_page`)다.
  - 잘라내기·복사·붙여넣기(`TodoPanel.cut_selected`/`copy_selected`/`paste`, 메모리의 `_clipboard`): 복사는 선택 항목을 하위와 함께 사본으로 담고(`todo_tree.subtrees`), 붙여넣을 때마다 새 id로 만든다(`todo_tree.clone`, 리마인더 알림 기록은 그대로). 잘라내기는 흐리게(`TodoRow.cut`) 표시만 해 두고 붙여넣으면 그 자리로 옮긴다(id 유지, 다른 페이지로도 - `page_id`를 바꾼 뒤 `move_many`). 잘라낸 것은 한 번만 붙여넣고, Esc·다시 복사하면 풀린다. 붙여넣는 자리는 지금 행 바로 아래이고, 잘라내기·복사할 때의 레벨(`_clipboard["levels"]`)을 지킨다(`todo_tree.paste_target`): 지금 행보다 깊으면 한 단계 아래(지금 행의 첫 하위)까지만 - 3레벨을 1레벨 아래에 붙이면 2레벨, 같으면 바로 뒤 형제, 얕으면 그 레벨의 상위 바로 뒤 형제. 잘라낸 묶음은 뒤 형제·첫 하위로 고르지 않는다. 선택이 없으면 최상위 맨 뒤. 잘라낸 묶음 안에 붙여넣으면 그대로 둔다. 복사·잘라내기는 시스템 클립보드에도 Markdown 체크리스트(`todo_export.to_text`: `- [ ] 할 일`, 하위는 2칸 들여쓰기, 구분선은 `---`)로 넣는다.
- TODO 드래그는 `QDrag`(Windows OLE `DoDragDrop`)를 쓰지 않는다. OLE 루프 동안은 휠이 오지 않고 커서를 움직일 때만 자동 스크롤되기 때문이다. 행의 마우스 grab으로 이동/놓음을 받고(`TodoRow.drag_*` 시그널), 반투명 ToolTip 창이 커서를 따라가며, `QTimer`가 목록 위·아래 끝에서 계속 스크롤한다. 놓은 뒤 이동은 `QTimer.singleShot(0)`으로 미룬다(놓은 행이 rebuild로 사라짐).
- TODO 태그: `todos.tag`(기본 `todo_store.TAGS` 중 하나 / 사용자 태그 id `custom-xxxxxxxx` / NULL이면 없음). 기본 색은 `todo_panel.TAG_COLORS`, 사용자 태그는 config.json `custom_tags`(`widget_config.custom_tags()`가 깨진 항목을 거름). 태그 메뉴는 기본 6색 → 태그 없음 → 사용자 태그 → "+ 태그 추가…"(`TagDialog`, 이름+색) 순이고, 선택 항목들이 모두 같은 태그면 그 칸을 강조색 테두리로 감싼다(checkable·checked 액션 + `QMenu::item:checked`, 체크 표시는 숨김, "태그 없음"은 표시 안 함). 이름·색 변경과 삭제는 설정창 Appearance "TODO 태그"에서 한다. 사용자 태그를 지우면 그 태그를 붙인 할 일은 DB 값은 그대로 두고 태그 없음으로 보인다. 설정창은 cfg의 목록을 id로 고쳐 저장한다(그사이 위젯 메뉴에서 추가한 태그를 덮어쓰지 않게). 체크박스 왼쪽 세로 막대로만 표시하고(글자색·기울임 없음) 태그가 없어도 막대 자리는 비워 둔다.
- TODO 페이지(엑셀 시트처럼 페이지마다 독립된 목록): `todo_pages`(id·이름·순서, 적어도 한 장)와 `todos.page_id`. v9 마이그레이션이 "페이지 1"을 만들고 기존 할 일을 모두 그리로 넣었다.
  - `TodoPanel._items`는 모든 페이지의 할 일이다. 리마인더 알림(`pop_due`)·팝업 완료는 모든 페이지에, 화면·검색 개수·완료 항목 정리·모두 접기·내보내기(화면 목록)·추가는 지금 페이지(`_page_items()`)에 적용한다. 페이지가 사라진 할 일은 불러올 때 첫 페이지로 옮긴다.
  - 표시(`ui/page_bar.PageBar`, "멍청한 뷰"): 위/아래는 [페이지 1][페이지 2]… 모든 페이지 이름 칩(`PageTabs`, 지금 페이지는 강조색 테두리, 긴 이름은 말줄임 + 툴팁, 이름 뒤에 체크 안 한 할 일 수 배지 - 하위 포함·구분선 제외, 0이면 숨김, 지금 페이지는 강조색·나머지는 회색, `TodoPanel._open_counts`를 `_rebuild`마다 `PageBar.set_counts`로 넘김) + [점들][+], 왼쪽/오른쪽은 세로 점과 +(칩은 숨기고 이름은 점의 툴팁). 칩이 폭을 넘치면 지금 페이지 칩이 보이게 옆으로 밀고, 잘린 쪽 끝은 흐리게 지운다(따로 그린 그림에 `CompositionMode_DestinationIn` 그라데이션). 점의 지금 페이지는 강조색 알약이고 넘길 때 알약이 옮겨 간다(`QVariantAnimation`). 칩·점 클릭·휠·Ctrl+PgUp/PgDown으로 넘기고(끝에서 멈춤), 칩 더블클릭·F2(고른 할 일이 없을 때)·우클릭으로 이름 바꾸기(`TagDialog(with_color=False)`), 우클릭으로 새 페이지·앞/뒤로 옮기기·삭제(다른 페이지 칩에서 우클릭하면 그 페이지로 넘어간 뒤 메뉴). 위치는 `TodoPanel._place_page_bar`가 레이아웃 칸(위: 검색 줄 위, 아래: 입력칸 위, 왼쪽/오른쪽: 목록 옆 `_middle`)을 옮긴다.
  - 페이지를 넘기면 선택은 풀고 검색 줄은 그대로 둬서 새 페이지에서 다시 거른다. 마지막으로 본 페이지는 cfg `todo_page`(없는 id면 첫 페이지).
  - 페이지 삭제는 마지막 한 장이면 막는다. 남은 할 일은 확인 창 뒤 한 묶음으로 삭제 이력에 넣고(펼친 순서) 앞 페이지(없으면 뒤)로 넘어간다. 되돌릴 때 스냅샷의 페이지가 없으면 지금 페이지로 넣고, 자리(상위·뒤 형제·하위)는 같은 페이지에 있을 때만 따른다. 지울 때의 "바로 뒤 형제"도 같은 페이지 안에서 찾는다.
  - 우패널 우클릭 "페이지로 이동"은 선택 항목을 하위와 함께 대상 페이지의 최상위 맨 뒤로 옮긴다(`TodoPanel.move_to_page`).
- TODO 검색·날짜별 보기: 평소에는 숨어 있고 Ctrl+F·우패널 우클릭 "검색"으로 목록 위에 `FilterBar`([전체][오늘 n][지연 n][예정 n] 칩 + 검색칸)를 연다. 칩(`todo_panel._Chip`)은 스타일시트 `border-radius`가 안티앨리어싱 없이 그려져 끝이 깨지므로 QPainter로 직접 그린다. 규칙은 `manager/todo_filter.py`에 있다. 날짜별 보기는 미완료 리마인더만 `todo_store.due_at`(미룬 시각 우선) 기준으로 나눈다(지연: 지남 / 오늘: 오늘 안에 남음 / 예정: 내일 이후). 검색은 토큰을 뺀 본문에서 대소문자 없이, 공백으로 나눈 단어가 모두 들어 있어야 맞다. 맞는 항목의 상위는 흐리게(`TodoRow.context`) 함께 보인다. 검색어가 바뀔 때마다 맞는 글자(`todo_filter.match_spans`)만 노란 배경(`to_html(marks=…)`)으로 칠했다가 2초 뒤 서서히 지운다(`TodoPanel._mark_hold`/`_mark_fade`, 칩만 바꾸면 다시 시작하지 않음, 상위 문맥 행은 칠하지 않음). 검색칸은 조합 중인 한글까지 바로 거른다(`text_input.PreeditLineEdit`). 거르는 중에는 드래그하지 않고, 숨은 항목은 선택에서 빠지며, 할 일을 추가하면 전체 보기로 돌아간다. Esc는 검색어를 지우고, 비어 있으면 줄을 닫는다(닫으면 필터도 풀림). 필터 상태는 저장하지 않는다.

## 데이터 저장 / 경로

- 사용자 데이터 위치: `%APPDATA%\TaskPin\`
  - `config.json` — 위젯 설정(위치·크기·투명도(`opacity`, 설정창 Appearance)·모드 등), 사용자 이름, `shortcuts`(동작별 QKeySequence PortableText), `snippets`(`[[":idea:", "💡"], ...]`), `appearance`(`widget_config.appearance()`가 깨진 값을 기본값으로 채움), `export_dir`(TODO·설정 내보내기 마지막 폴더), `custom_tags`(사용자 TODO 태그), `confirm_delete`·`undo_limit`(TODO 삭제 확인·되돌릴 수 있는 삭제 수), `todo_page`(마지막으로 본 TODO 페이지 id), `app_icon`(트레이·창 아이콘 `dark`/`light`). 크기는 세로 모드 `vertical_width`·`height`, 가로 모드 `width`·`horizontal_height`를 따로 저장한다. 세로 모드는 폭 280~364(1.3배)·높이 최소~583(486의 1.2배), 가로 모드는 폭 540~810·높이 최소~1.5배. 높이는 하단 핸들, 폭은 우측 핸들로 조절하고, 좌측 칼럼은 가로 모드에서만 폭이 고정이다
  - `taskpin.db` — SQLite: TODO(계층·태그·접힘 포함), 정리된 완료 항목, 지운 TODO 이력(`todo_deletions`, 스키마 v8), TODO 페이지(`todo_pages` + `todos.page_id`, 스키마 v9), Task 등록 정보(업무명·상세 업무·시간·완료/해제)
  - `taskpin-backup-YYYYMMDD-HHMMSS.db` — "모든 데이터 초기화" 직전의 DB 백업 (앱은 다시 읽지 않는다)
- 구분선: 하이픈만 3개 이상 적은 할 일(`todo_store.is_separator`, 우클릭 "아래에 구분선 추가"는 `"---"`)은 체크박스·글자 대신 가로선으로 그린다(`TodoRow.separator`, 숨긴 글자 칸이 자리를 지켜 행 높이와 ✕ 자리가 보통 행과 같다). 고치지 않고(더블클릭·F2 무시), 하위를 두지 않으며(드래그 가운데 = 다음 행 앞, 구분선을 고르고 입력하면 그 바로 아래 형제로), 검색어로 걸리지 않는다(`todo_filter.matches`). "아래에 구분선 추가"는 누른 행 바로 아래 형제로 넣고 완료된 상위 아래면 구분선도 완료로 둔다(상위가 미완료로 돌아가지 않게). 내보내기에서는 `---` 가로줄이다.
- "완료 항목 정리"(`TodoPanel.clear_done`)는 행을 지우지 않고 보관 상태로 바꾼다.
- TODO 삭제(행의 ✕ / 우클릭 "삭제")는 모두 `TodoPanel._delete`를 거쳐 되돌릴 수 있게 남긴다.
  - 항목마다 지우기 전에 `todo_tree.removal`로 자리(상위·바로 뒤 형제·한 단계 올라갈 하위)를 남기고, 지울 때의 항목 전체(JSON 스냅샷)와 함께 `todo_trash.record`에 한 묶음(batch)으로 기록한다.
  - 우클릭 "삭제 이력"은 최근 `undo_limit`번의 삭제 중 되돌리지 않은 묶음을 최신 순으로 보여준다. 누르면 묶음을 거꾸로 `todo_tree.restore` 한다(상위·뒤 형제가 없어졌으면 최상위·맨 뒤, 올라갔던 하위는 아직 그 자리에 있을 때만 다시 하위로). 되돌려도 이력 행은 지우지 않고 `restored_at`만 남긴다.
  - 행의 ✕와 우클릭 "삭제"는 모두 `ClockWidget._confirm_todo_delete`로 먼저 묻는다(`ConfirmDialog(remember_text="다시 묻지 않음")`). 체크하고 삭제하면 cfg `confirm_delete=False`, 설정창 Application에서 다시 켠다. 여러 개를 지우면 문구에 개수를 넣는다.
  - PySide6: `menu.addMenu("제목")`으로 만든 서브메뉴에 `addAction(글자, 함수)`를 넣고 그 서브메뉴 참조가 사라지면(헬퍼 함수가 끝나면) 서브메뉴가 지워진다. 헬퍼에서 서브메뉴를 만들 때는 `QMenu("제목", menu)` + `menu.addMenu(sub)`로 부모를 준다.
- "TODO 내보내기"(우패널 우클릭 서브메뉴: 화면 목록 / 보관 항목 전체)는 Markdown 체크리스트(.md, UTF-8)로 저장한다. 화면 목록은 지금 페이지라 제목(`# Task알림 TODO — 페이지 · 화면 목록`)과 파일 이름(`TaskPin-TODO-페이지-YYYYMMDD.md`, `todo_export.filename_part`가 쓸 수 없는 글자를 `_`로)에 페이지 이름을 넣는다(보관 항목은 모든 페이지라 넣지 않음). 접힌 항목의 하위도 모두 쓴다(접힘은 화면 표시일 뿐). 하위는 2칸 들여쓰기, 보관 항목은 보관 날짜별 섹션. 보관 항목은 섹션마다 상위 사슬을 함께 쓴다(`todo_export._with_ancestors`) - 상위가 화면 목록에 남아 있으면(미완료) `- [ ]`로, 다른 날짜에 보관됐으면 그 섹션에도 다시 나온다. 그래야 하위가 다른 항목의 하위나 최상위처럼 보이지 않는다. 텍스트를 그대로 써서 `(@...)` 리마인더 토큰이 Obsidian에서도 읽힌다.
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

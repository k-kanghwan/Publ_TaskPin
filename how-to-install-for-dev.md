# 배포 파일 만들기 (개발자용)

배포 파일은 **설치본(`dist/TaskPin-<버전>-setup.exe`) 하나**다. Nuitka로 exe 폴더를 빌드한 뒤, 그 폴더를 Inno Setup으로 묶는다.

## 0. 준비 (처음 한 번만)

```powershell
pip install -r requirements-dev.txt     # PySide6, pytest, nuitka, watchfiles
```

- **Inno Setup 6**: 사용자 단위로 설치하면 `%LOCALAPPDATA%\Programs\Inno Setup 6`에, 관리자 권한으로 설치하면 `C:\Program Files (x86)\Inno Setup 6`에 들어간다. `ISCC.exe`는 PATH에 등록되지 않으므로 아래에서는 전체 경로로 실행한다.
- **C 컴파일러**: Nuitka가 처음 빌드할 때 MinGW 등을 내려받는다. `--assume-yes-for-downloads` 옵션이 있어서 묻지 않고 진행한다.

## 1. 버전 올리기 (새 버전을 낼 때)

루트의 `version.py` 한 곳만 고친다. 앱 안의 `VERSION`과 Nuitka `--product-version`이 모두 이 값을 쓴다.

```python
VERSION = "0.1.0"
```

설치본 버전은 빌드된 exe에서 자동으로 읽어 오므로 `installer/TaskPin.iss`는 고치지 않는다.

## 2. 테스트 → exe 빌드

```powershell
pytest
python -m nuitka TaskPin.py
```

- 빌드 옵션(standalone, pyside6 플러그인, 콘솔 숨김, 아이콘, exe 이름)은 `TaskPin.py`의 `# nuitka-project:` 주석에 모두 들어 있어서 추가 인자가 필요 없다.
- 결과: `build\TaskPin.dist\Task알림.exe`. exe 하나가 아니라 폴더 전체가 실행 단위다.
- 이 단계에서 `build\TaskPin.dist\Task알림.exe`를 직접 실행해 트레이 아이콘과 위젯이 뜨는지 확인한다.

## 3. 설치본 만들기

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\TaskPin.iss
```

- Inno Setup을 관리자 권한으로 설치했다면 `& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\TaskPin.iss`로 실행한다.
- 성공하면 마지막에 `Successful compile`이 출력된다.
- 결과: `dist\TaskPin-<버전>-setup.exe`. 배포할 파일은 이것이다.

## 설치본 동작

- 관리자 권한 없이 사용자 단위로 `%LOCALAPPDATA%\Programs\TaskPin`에 설치된다.
- 앱이 실행 중이면 설치와 제거가 막힌다(`AppMutex=TaskPin`). 업데이트하기 전에 트레이에서 앱을 종료해야 한다.
- 제거하면 자동 실행 레지스트리 값(`HKCU\...\Run\TaskPin`)만 지우고, 사용자 데이터(`%APPDATA%\TaskPin`)는 남긴다.

## 참고

- 앱 아이콘(`ico/taskpin_icon_A_memo.svg`)을 바꿨다면 빌드 전에 `python tools/make_ico.py`로 `ico/taskpin.ico`를 다시 만든다.
- 같은 버전으로 다시 빌드하면 `build/`와 `dist/`의 결과물을 덮어쓴다.
- Inno Setup 6.7 이상은 컴파일러가 "Non-commercial use only"로 표시된다. 상업적으로 배포하려면 라이선스를 확인해야 한다.

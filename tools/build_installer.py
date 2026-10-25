"""설치본 한 번에 만들기: Nuitka 빌드 -> ISCC 컴파일 -> dist 결과 확인

    python tools/build_installer.py

- Nuitka 옵션은 TaskPin.py 의 # nuitka-project: 주석에 모두 있으므로 인자를 더 주지 않는다.
- ISCC.exe 는 PATH 에 없으므로 Inno Setup 6 의 사용자/관리자 설치 경로에서 찾는다.
  Nuitka 를 몇 분 돌린 뒤 실패하지 않도록 빌드 전에 먼저 확인한다.
- 결과: dist/TaskPin-<버전>-setup.exe (버전은 version.py 의 VERSION)
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = "TaskPin.py"
ISS = os.path.join("installer", "TaskPin.iss")
DIST_EXE = os.path.join(ROOT, "build", "TaskPin.dist", "Task알림.exe")


def log(msg: str):
    print(f"[build] {msg}", flush=True)


def fail(msg: str):
    sys.exit(f"[build] 실패: {msg}")


def read_version() -> str:
    """TaskPin.py 의 nuitka-project-set 과 같은 방식으로 version.py 에서 읽는다"""
    with open(os.path.join(ROOT, "version.py"), encoding="utf-8") as f:
        match = re.search(r'^VERSION = "(.+)"', f.read(), re.M)
    if not match:
        fail("version.py 에서 VERSION 을 찾지 못했습니다.")
    return match.group(1)


def find_iscc() -> str | None:
    found = shutil.which("ISCC")
    if found:
        return found
    for base in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(base)
        if not root:
            continue
        sub = ("Programs", "Inno Setup 6") if base == "LOCALAPPDATA" else ("Inno Setup 6",)
        path = os.path.join(root, *sub, "ISCC.exe")
        if os.path.isfile(path):
            return path
    return None


def run(cmd: list[str]):
    code = subprocess.run(cmd, cwd=ROOT).returncode
    if code != 0:
        fail(f"{os.path.basename(cmd[0])} 종료 코드 {code}")


def main():
    started = time.monotonic()
    version = read_version()

    if importlib.util.find_spec("nuitka") is None:
        fail("nuitka 가 없습니다. pip install -r requirements-dev.txt 를 먼저 실행하세요.")
    iscc = find_iscc()
    if iscc is None:
        fail(
            "ISCC.exe 를 찾지 못했습니다. Inno Setup 6 을 설치하세요.\n"
            "        winget install JRSoftware.InnoSetup  (또는 https://jrsoftware.org/isdl.php)"
        )
    log(f"버전 {version}, ISCC: {iscc}")

    log(f"[1/2] Nuitka 빌드: {MAIN}")
    run([sys.executable, "-m", "nuitka", MAIN])
    if not os.path.isfile(DIST_EXE):
        fail(f"빌드 결과가 없습니다: {DIST_EXE}")

    log(f"[2/2] 설치본 컴파일: {ISS}")
    run([iscc, ISS])

    setup = os.path.join(ROOT, "dist", f"TaskPin-{version}-setup.exe")
    if not os.path.isfile(setup):
        fail(f"설치본이 없습니다: {setup}")
    size_mb = os.path.getsize(setup) / 1024 / 1024
    elapsed = time.monotonic() - started
    log(f"완료: {setup} ({size_mb:.1f} MB, {elapsed / 60:.1f}분)")


if __name__ == "__main__":
    main()

"""개발용 실행기: 소스(.py)를 저장하면 앱을 다시 띄운다

    python tools/dev_run.py

VS Code 의 "Task알림: 디버그 (저장 시 재시작)" 구성이 이 스크립트를 실행한다.
debugpy(subProcess)가 자식 앱 프로세스에도 붙으므로 재시작 후에도 중단점이 동작한다.
앱이 스스로 종료되면(트레이 "종료", 예외) 다음 저장 때 다시 띄운다.
"""

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = "TaskPin.py"
WATCH_DIRS = ("manager", "ui")
POLL_SEC = 0.5
DEBOUNCE_SEC = 0.3  # 여러 파일을 한 번에 저장할 때 한 번만 재시작
STOP_TIMEOUT_SEC = 3


def snapshot() -> dict:
    """감시 대상 .py 파일별 수정 시각"""
    files = [os.path.join(ROOT, MAIN)]
    for name in WATCH_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, name)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            files += [os.path.join(dirpath, f) for f in filenames if f.endswith(".py")]

    mtimes = {}
    for path in files:
        try:
            mtimes[path] = os.stat(path).st_mtime
        except OSError:
            pass  # 저장 도중 잠깐 사라지는 파일
    return mtimes


def changed_files(old: dict, new: dict) -> list:
    return sorted(
        os.path.relpath(p, ROOT)
        for p in old.keys() | new.keys()
        if old.get(p) != new.get(p)
    )


def start_app() -> subprocess.Popen:
    print(f"[dev_run] 실행: {MAIN}", flush=True)
    return subprocess.Popen([sys.executable, MAIN], cwd=ROOT)


def stop_app(proc: subprocess.Popen):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(STOP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main():
    mtimes = snapshot()
    proc = start_app()
    exited_reported = False
    try:
        while True:
            time.sleep(POLL_SEC)

            if proc.poll() is not None and not exited_reported:
                exited_reported = True
                print(
                    f"[dev_run] 앱 종료 (코드 {proc.returncode}) - 저장하면 다시 실행합니다",
                    flush=True,
                )

            current = snapshot()
            if current == mtimes:
                continue

            # 저장이 끝날 때까지 기다린다
            time.sleep(DEBOUNCE_SEC)
            current = snapshot()
            print(
                f"[dev_run] 변경: {', '.join(changed_files(mtimes, current))}",
                flush=True,
            )
            mtimes = current

            stop_app(proc)
            proc = start_app()
            exited_reported = False
    except KeyboardInterrupt:
        pass
    finally:
        stop_app(proc)


if __name__ == "__main__":
    main()

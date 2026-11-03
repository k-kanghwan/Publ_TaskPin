"""개발용 실행기: 소스(.py)를 저장하면 앱을 다시 띄운다 (watchfiles)

    python tools/dev_run.py

VS Code 의 "Task알림: 디버그 (저장 시 재시작)" 구성이 이 스크립트를 실행한다.
- target 은 명령 문자열이 아니라 함수로 준다. Windows 에서 명령 문자열은
  shlex.split(posix=False) 를 거쳐 공백 있는 python 경로의 따옴표가 깨질 수 있다.
- 함수 target 은 multiprocessing spawn 자식에서 돈다. debugpy(subProcess)가
  이 자식에도 붙으므로 재시작 후에도 중단점이 동작한다.
- 앱이 스스로 종료되면(트레이 "종료", 예외) 다음 저장 때 다시 띄운다.
- 디버그 데이터(.debug_appdata)는 처음 띄울 때만 새로 만든다(tools/debug_seed.prepare). 저장해서 다시 띄울
  때는 TASKPIN_DEBUG_KEEP=1 을 붙여 시험하던 상태를 그대로 둔다.
"""

import os
import runpy
import sys

from watchfiles import PythonFilter, run_process

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = "TaskPin.py"
WATCH_PATHS = (MAIN, "manager", "ui")
# tools/debug_seed.KEEP_ENV - "1" 이면 디버그 데이터를 새로 만들지 않고 이어서 쓴다
KEEP_ENV = "TASKPIN_DEBUG_KEEP"


def run_app():
    """자식 프로세스에서 TaskPin.py 를 __main__ 으로 실행"""
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.argv = [MAIN]
    runpy.run_path(MAIN, run_name="__main__")


def on_change(changes):
    files = sorted({os.path.relpath(path, ROOT) for _, path in changes})
    print(f"[dev_run] 변경: {', '.join(files)} - 다시 실행 (디버그 데이터 유지)", flush=True)
    # 다음 자식부터 (spawn 자식은 이 프로세스의 환경변수를 물려받는다)
    os.environ[KEEP_ENV] = "1"


def main():
    print(f"[dev_run] 실행: {MAIN}", flush=True)
    run_process(
        *(os.path.join(ROOT, p) for p in WATCH_PATHS),
        target=run_app,
        callback=on_change,
        watch_filter=PythonFilter(),
    )


if __name__ == "__main__":
    main()

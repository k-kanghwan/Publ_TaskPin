"""경로 규칙

  - 번들 리소스(아이콘 등): 소스/빌드 폴더 기준 (__file__)
  - 사용자 데이터(config.json, taskpin.db): os_win.user_data_dir()

CWD 는 자동 실행 시 system32 가 되는 등 믿을 수 없으므로 어떤 경로도 CWD 에 기대지 않는다.
"""

import os

from manager import os_win


# manager/ 의 상위 = 저장소 루트 (Nuitka standalone 에서는 TaskPin.dist 폴더)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel_path: str) -> str:
    return os.path.join(_BASE_DIR, rel_path)


def data_path(name: str) -> str:
    """사용자 데이터 파일 경로. 폴더가 없으면 만든다."""
    data_dir = os_win.user_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, name)

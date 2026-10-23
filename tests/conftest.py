import pytest

from manager import db


@pytest.fixture
def temp_db(tmp_path):
    """테스트마다 새 임시 DB (실제 %APPDATA% 의 taskpin.db 는 건드리지 않음)"""
    path = tmp_path / "test.db"
    db.connect(str(path))
    yield path
    db.close()

import pytest
from app.config import SAMPLE
from app.pipeline import calculate
@pytest.fixture
def raw(): return SAMPLE.read_text(encoding='utf-8-sig')
@pytest.fixture
def ctx(): return calculate()

@pytest.fixture
def multi_ctx():
    from app.config import MULTI_SAMPLE
    return calculate(MULTI_SAMPLE.read_text(encoding='utf-8-sig'))
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_DB',str(tmp_path/'db.sqlite3'))
    from app.main import app
    app.config['TESTING']=True
    return app.test_client()

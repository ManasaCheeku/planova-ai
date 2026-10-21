import pytest


@pytest.fixture(autouse=True)
def isolate_dashboard_database(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANOVA_DB_PATH", str(tmp_path / "planova-test.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

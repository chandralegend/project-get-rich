import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Every test gets its own empty data directory and no real notifications or pings."""
    monkeypatch.setenv("GETRICH_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("GETRICH_NOTIFY", "0")
    monkeypatch.delenv("GETRICH_HEARTBEAT_URL", raising=False)
    return tmp_path / "data"

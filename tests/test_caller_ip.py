from fastapi.testclient import TestClient

from api.caller_ip import STUB_IP, resolve_caller_ip
from api.main import app


class _Client:
    def __init__(self, host):
        self.host = host


class _Request:
    def __init__(self, host="", forwarded=""):
        self.client = _Client(host) if host else None
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


def test_public_forwarded_address_is_kept():
    ip, simulated = resolve_caller_ip(_Request("127.0.0.1", "203.150.12.8, 10.0.0.1"))
    assert ip == "203.150.12.8"
    assert simulated is False


def test_loopback_uses_the_thai_stub():
    ip, simulated = resolve_caller_ip(_Request("127.0.0.1"))
    assert ip == STUB_IP
    assert simulated is True


def test_session_and_case_store_the_stub(client=None):
    del client
    with TestClient(app) as test_client:
        session = test_client.post("/session")
        assert session.status_code == 200
        body = session.json()
        assert body["caller_ip"] == STUB_IP
        assert body["simulated"] is True
        assert "DEMO" in body["note"]
        created = test_client.post("/cases", json={"fixture_id": "F01"})
        assert created.status_code == 200
        resources = created.json()["case"]["resources"]
        assert resources["caller_ip"] == STUB_IP
        assert resources["caller_ip_simulated"] is True

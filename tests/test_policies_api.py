"""Policy service and HTTP API. No live model. No remote fetch in the default path."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from policies.schema import LanguageText, NormalisedRule
from policies.service import PolicyService, get_service
from policies.sources.candidates import CANDIDATES
from policies.sources.local_yaml import LocalYamlAdapter
from system1.labels import hypotheses
from system2.sapling_policy import build_sapling_input

BANNED = ("reliefweb.int", "reliefweb.org", "disaster.go.th", "ddpm.go.th")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class _StubAdapter:
    source_id = "stub_synthetic"

    def fetch(self) -> dict:
        return {"marker": "synthetic"}

    def version(self, fetched: dict) -> str:
        return "stub-v1"

    def normalise(self, fetched: dict, *, source_version: str):
        rule = NormalisedRule(
            rule_id="SYNTH-ADAPTER-RULE",
            jurisdiction="TH",
            domain="triage",
            languages={
                "en": LanguageText("Synthetic adapter rule for a test household.", "", False),
                "th": LanguageText("กฎทดสอบสำหรับครัวเรือนสมมติ", "", False),
            },
            effective_from=None,
            effective_to=None,
            effective_stated=None,
            effective_note="",
            source_url="https://example.com/synthetic-policy",
            license="Synthetic test text. Not a government instrument.",
            verified=True,
            source_id=self.source_id,
            source_version=source_version,
            retrieved="2026-10-24",
            status="verified",
            topic="triage",
            checks=("triage",),
            caveat="",
            locator="test",
            source_excerpt="Synthetic adapter rule.",
        )
        return [rule], []


def test_default_service_is_local_yaml_only():
    body = get_service().sources()
    assert [row["source_id"] for row in body["live"]] == ["local_yaml"]
    assert body["candidates"]
    ids = {row["source_id"] for row in body["candidates"]}
    assert "sphere_handbook_api" in ids
    assert "gdcatalog_ratchakitcha" in ids
    assert "ocha_hpc_fts" in ids
    for row in body["candidates"]:
        assert row["todo"] == "TODO_HUMAN"
        blob = " ".join(str(value) for value in row.values()).lower()
        for host in BANNED:
            assert host not in blob
    assert len(body["candidates"]) == len(CANDIDATES)


def test_list_filters_jurisdiction_and_domain(client):
    response = client.get("/policies", params={"jurisdiction": "TH", "domain": "triage", "lang": "th"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["rules"])
    assert body["count"] > 0
    assert response.headers["X-Policy-Corpus-Version"] == body["version"]
    for rule in body["rules"]:
        assert rule["jurisdiction"] == "TH"
        assert rule["domain"] == "triage"
        assert "en" in rule["languages"] and "th" in rule["languages"]
        assert rule["effective_from"] is None


def test_one_rule_keeps_the_printed_meal_ceiling(client):
    response = client.get("/policies/MOF-2569-FOOD")
    assert response.status_code == 200
    rule = response.json()["rule"]
    assert rule["verified"] is True
    assert rule["jurisdiction"] == "TH"
    assert rule["domain"] == "aid_eligibility"
    assert rule["effective_stated"] == "6 March B.E. 2569"
    assert rule["effective_from"] is None
    assert "80" in rule["languages"]["en"]["text"]
    assert "๘๐" in rule["source_excerpt"]
    assert "2026-03-06" not in rule["languages"]["en"]["text"]
    missing = client.get("/policies/MOF-2569-NOT-A-RULE")
    assert missing.status_code == 404


def test_flood_rules_are_served(client):
    listed = client.get("/policies", params={"domain": "triage", "jurisdiction": "intl"})
    assert listed.status_code == 200
    ids = {row["rule_id"] for row in listed.json()["rules"]}
    assert "FLOOD-WATER-DEPTH" in ids
    assert "EA-FLOOD-WARNINGS" in ids
    assert "UK-BOAT-TEAMS" in ids
    depth = client.get("/policies/FLOOD-WATER-DEPTH").json()["rule"]
    assert depth["verified"] is True
    assert depth["jurisdiction"] == "intl"
    assert "6 inches" in depth["source_excerpt"]
    health = client.get("/policies/CDC-FLOOD-HEALTH").json()["rule"]
    assert health["domain"] == "safeguarding"
    assert "Leptospirosis (not common)" in health["source_excerpt"]
    gap = client.get("/policies/FLOOD-BOAT-ORDER").json()["rule"]
    assert gap["verified"] is False
    assert "Team assumption" in gap["text"]


def test_labels_endpoint_matches_system1_reader(client):
    response = client.get("/policies/labels", params={"lang": "th"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 16
    rows = hypotheses("th", version=body["version"])
    assert [row["id"] for row in rows] == [row["id"] for row in body["labels"]]
    red = next(row for row in rows if row["id"] == "niems_red_critical")
    assert "ฉุกเฉิน" in red["hypothesis"]
    assert red["languages"]["th"]["quotation"] is False


def test_match_returns_candidates_without_a_verdict(client):
    response = client.post(
        "/policies/match",
        json={
            "evidence": "Synthetic household H-204 asked about prepared meals after the flood.",
            "claim": "The meal ceiling should be applied to synthetic household H-204.",
            "jurisdiction": "TH",
            "domain": "aid_eligibility",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "verdict" not in body
    assert body["candidates"]
    assert body["candidates"][0]["rule_id"] == "MOF-2569-FOOD"
    assert body["candidates"][0]["verified"] is True
    again = client.post(
        "/policies/match",
        json={
            "evidence": "Synthetic household H-204 asked about prepared meals after the flood.",
            "claim": "The meal ceiling should be applied to synthetic household H-204.",
            "jurisdiction": "TH",
            "domain": "aid_eligibility",
        },
    )
    assert again.json() == body


def test_version_pin_survives_a_new_service(tmp_path, client):
    service = PolicyService(pin_dir=tmp_path)
    pinned = service.pin_run("eval-synthetic-1")
    other = PolicyService(pin_dir=tmp_path)
    listed = other.list_rules(run_id="eval-synthetic-1")
    assert listed["version"] == pinned["version"]
    assert listed["origin"] == "pin"
    assert listed["rules"]
    mismatch = client.get("/policies", params={"version": "0" * 64})
    assert mismatch.status_code == 409
    bad = client.get("/policies", params={"version": "not-a-hash"})
    assert bad.status_code == 400


def test_api_pin_then_read(client):
    created = client.post("/policies/pins", json={"run_id": "eval-api-synthetic"})
    assert created.status_code == 200
    version = created.json()["version"]
    fetched = client.get("/policies/MOF-2569-FOOD", params={"run_id": "eval-api-synthetic"})
    assert fetched.status_code == 200
    assert fetched.json()["version"] == version
    assert fetched.json()["origin"] == "pin"


def test_second_adapter_is_merged_and_sapling_reads_the_service(monkeypatch, tmp_path):
    merged = PolicyService(adapters=[LocalYamlAdapter(), _StubAdapter()], pin_dir=tmp_path)
    assert "SYNTH-ADAPTER-RULE" in merged.known_ids()
    assert "MOF-2569-FOOD" in merged.known_ids()

    def boom(rule_id: str):
        raise AssertionError(f"YAML loader was called for {rule_id}")

    monkeypatch.setattr("policies.corpus.get_rule", boom)
    built = build_sapling_input(
        ["MOF-2569-FOOD"],
        "Synthetic household H-204 reported a flooded kitchen.",
        "Synthetic household H-204 should be paid the meal ceiling automatically.",
    )
    assert built["included_rule_ids"] == ["MOF-2569-FOOD"]
    assert built["corpus_version"]
    assert "corpus_version:" in built["policy"]
    assert "๘๐" in built["policy"]

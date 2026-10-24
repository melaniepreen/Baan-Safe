"""Policy corpus HTTP API. Reads the policy service, not the YAML files."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from policies.service import PolicyError, get_service

router = APIRouter(prefix="/policies", tags=["policies"])


class MatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: str = ""
    claim: str = ""
    jurisdiction: Literal["TH", "intl"] | None = None
    domain: Literal["aid_eligibility", "safeguarding", "triage"] | None = None
    lang: Literal["en", "th"] = "en"
    version: str | None = None
    run_id: str | None = None


class PinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=80)


def _call(action):
    try:
        return action()
    except PolicyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None


def _cache(response: Response, body: dict) -> dict:
    version = str(body.get("version") or "")
    if version:
        response.headers["ETag"] = f'"{version}"'
        response.headers["X-Policy-Corpus-Version"] = version
        response.headers["Cache-Control"] = "public, max-age=300"
    return body


@router.get("")
def list_policies(
    response: Response,
    jurisdiction: Literal["TH", "intl"] | None = None,
    domain: Literal["aid_eligibility", "safeguarding", "triage"] | None = None,
    lang: Literal["en", "th"] = "en",
    version: str | None = None,
    run_id: str | None = None,
) -> dict:
    body = _call(
        lambda: get_service().list_rules(
            jurisdiction=jurisdiction,
            domain=domain,
            lang=lang,
            version=version,
            run_id=run_id,
        )
    )
    return _cache(response, body)


@router.get("/labels")
def list_labels(
    response: Response,
    lang: Literal["en", "th"] = "en",
    version: str | None = None,
    run_id: str | None = None,
) -> dict:
    body = _call(
        lambda: get_service().labels(lang=lang, version=version, run_id=run_id)
    )
    return _cache(response, body)


@router.get("/sources")
def list_sources(response: Response) -> dict:
    body = _call(lambda: get_service().sources())
    return _cache(response, body)


@router.post("/pins")
def pin_run(body: PinIn) -> dict:
    return _call(lambda: get_service().pin_run(body.run_id))


@router.post("/match")
def match_policies(body: MatchIn, response: Response) -> dict:
    found = _call(
        lambda: get_service().match(
            evidence=body.evidence,
            claim=body.claim,
            jurisdiction=body.jurisdiction,
            domain=body.domain,
            lang=body.lang,
            version=body.version,
            run_id=body.run_id,
        )
    )
    return _cache(response, found)


@router.get("/{rule_id}")
def get_policy(
    rule_id: str,
    response: Response,
    lang: Literal["en", "th"] = "en",
    version: str | None = Query(default=None),
    run_id: str | None = None,
) -> dict:
    body = _call(
        lambda: get_service().get_rule(
            rule_id,
            lang=lang,
            version=version,
            run_id=run_id,
        )
    )
    return _cache(response, body)

"""Banyan Sapling client. Owner: Melanie.

The committed client is the stub (`sapling.client: stub`). It returns the
labels in `mocks/sapling_stub/` and does not load a GPU. `SAPLING_IMPL=live`
refuses while hosting, the GPU, the model id, or Thai handling is still
TODO_HUMAN, and it does not open a socket.

The checkpoint is MubitLabs/banyan-sapling. Its own labels are `supported`,
`violation`, `insufficient_information`, and `inconsistent_context`, plus a
calibrated status of `unsure`. This client speaks the BaanSafe names:
supported, violation, missing, contradicted, unsure.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from config.settings import DecisionRequired, require_decision, unset_decisions
from paths import ROOT

PUBLISHED_MODEL_ID = "MubitLabs/banyan-sapling"
MAX_INPUT_TOKENS = 16384
# Ceiling used before the checkpoint tokenizer is available. The loader's
# encode() refuses at 16,384 encoded tokens and does not truncate.
CHARS_PER_TOKEN_CEILING = 4
STUB_DIR = ROOT / "mocks" / "sapling_stub"

VERDICTS = ("supported", "violation", "missing", "contradicted", "unsure")
ACTIONS = {
    "supported": "proceed",
    "violation": "block",
    "missing": "human_handoff",
    "contradicted": "human_handoff",
    "unsure": "human_handoff",
}
# Checkpoint label -> BaanSafe verdict. `unsure` is a calibrated status, not
# one of the four softmax classes.
MODEL_LABELS = {
    "supported": "supported",
    "violation": "violation",
    "insufficient_information": "missing",
    "inconsistent_context": "contradicted",
    "missing": "missing",
    "contradicted": "contradicted",
    "unsure": "unsure",
}
CHECKS = ("aid_eligibility", "denial")
_LIVE_DECISIONS = (
    "sapling.hosting",
    "sapling.gpu",
    "sapling.model_id",
    "sapling.thai_handling",
)


@dataclass(frozen=True)
class SaplingVerdict:
    verdict: str
    action: str
    probabilities: dict[str, float]
    check: str | None
    stub: bool
    model_id: str
    probabilities_are_calibrated: bool
    notes: str = ""
    input_limit_tokens: int = MAX_INPUT_TOKENS


def one_hot(verdict: str) -> dict[str, float]:
    return {name: (1.0 if name == verdict else 0.0) for name in VERDICTS}


def make_verdict(
    verdict: str,
    *,
    check: str | None,
    stub: bool,
    notes: str = "",
    probabilities: dict[str, float] | None = None,
    calibrated: bool = False,
    model_id: str = PUBLISHED_MODEL_ID,
) -> SaplingVerdict:
    if verdict not in ACTIONS:
        raise ValueError(f"Unknown Sapling verdict {verdict!r}.")
    probs = one_hot(verdict) if probabilities is None else dict(probabilities)
    missing = [name for name in VERDICTS if name not in probs]
    if missing:
        raise ValueError("Probabilities are missing " + ", ".join(missing) + ".")
    return SaplingVerdict(
        verdict=verdict,
        action=ACTIONS[verdict],
        probabilities={name: float(probs[name]) for name in VERDICTS},
        check=check,
        stub=stub,
        model_id=model_id,
        probabilities_are_calibrated=calibrated,
        notes=notes,
    )


def load_stub_cases() -> list[dict]:
    cases = []
    for path in sorted(STUB_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_path"] = str(path.relative_to(ROOT))
        cases.append(payload)
    return cases


def client_mode() -> str:
    """`SAPLING_IMPL` overrides `sapling.client`. An unset client stays a stub."""
    env = os.environ.get("SAPLING_IMPL", "").strip().lower()
    if env in {"stub", "live"}:
        return env
    if env:
        raise DecisionRequired(f"SAPLING_IMPL {env!r} must be stub or live.")
    if unset_decisions(["sapling.client"]):
        return "stub"
    value = require_decision("sapling.client")
    if value == "stub":
        return "stub"
    if value == "live":
        return "live"
    raise DecisionRequired(
        f"config/decisions.yaml:sapling.client is {value!r}. Use stub or live."
    )


def estimate_tokens(policy: str, evidence: str, claim: str) -> int:
    return (len(policy) + len(evidence) + len(claim)) // CHARS_PER_TOKEN_CEILING


def check_request(policy: str, evidence: str, claim: str) -> None:
    for name, value in (("policy", policy), ("evidence", evidence), ("claim", claim)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a nonempty string.")
    estimate = estimate_tokens(policy, evidence, claim)
    if estimate > MAX_INPUT_TOKENS:
        raise ValueError(
            f"Input is about {estimate} tokens. Sapling's limit is "
            f"{MAX_INPUT_TOKENS} encoded tokens, and the checkpoint does not truncate."
        )


def verdict_from_model_output(payload: dict, *, check: str | None = None) -> SaplingVerdict:
    """Map a checkpoint response into a BaanSafe verdict.

    `probabilities` on the checkpoint are the temperature-scaled softmax over
    the four classes. `status` may be `unsure` when the prediction set is not
    a single label. This function does not call the model.
    """
    status = payload.get("status")
    if status not in MODEL_LABELS:
        raise ValueError(f"Sapling status {status!r} is not a known verdict.")
    verdict = MODEL_LABELS[status]
    raw = payload.get("probabilities") or {}
    mapped = {name: 0.0 for name in VERDICTS}
    for label, prob in raw.items():
        key = MODEL_LABELS.get(label)
        if key is None or key == "unsure":
            continue
        mapped[key] = float(prob)
    if verdict == "unsure":
        used = sum(mapped[name] for name in VERDICTS if name != "unsure")
        mapped["unsure"] = max(0.0, 1.0 - used)
    model_id = str(payload.get("model") or PUBLISHED_MODEL_ID)
    return make_verdict(
        verdict,
        check=check,
        stub=False,
        calibrated=True,
        probabilities=mapped,
        model_id=model_id,
        notes="Mapped from the checkpoint status and class probabilities.",
    )


def verify(
    policy: str,
    evidence: str,
    claim: str,
    *,
    check: str | None = None,
    language: str = "en",
) -> SaplingVerdict:
    """Classify one claim. The stub path never loads weights."""
    _refuse_unset_language(language)
    check_request(policy, evidence, claim)
    if client_mode() == "live":
        return _verify_live(policy, evidence, claim, check)
    return _verify_stub(policy, evidence, claim, check)


def _refuse_unset_language(language: str) -> None:
    if language.strip().lower() == "en":
        return
    handling = unset_decisions(["sapling.thai_handling"])
    if handling:
        raise DecisionRequired(
            "config/decisions.yaml:sapling.thai_handling is TODO_HUMAN. "
            "Refusing to translate and refusing to send non-English text. "
            "The model card says the evaluated language is English."
        )
    chosen = require_decision("sapling.thai_handling")
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        f"sapling.thai_handling is {chosen!r}. This client does not apply it."
    )


def _verify_stub(
    policy: str,
    evidence: str,
    claim: str,
    check: str | None,
) -> SaplingVerdict:
    for case in load_stub_cases():
        if (case["policy"], case["evidence"], case["claim"]) != (policy, evidence, claim):
            continue
        return make_verdict(
            case["expected_verdict"],
            check=check or case.get("check"),
            stub=True,
            notes="Stub label from mocks/sapling_stub. Not a model probability.",
        )
    return make_verdict(
        "unsure",
        check=check,
        stub=True,
        notes="No stub triple matched. Unsure hands the claim to a human.",
    )


def _verify_live(
    policy: str,
    evidence: str,
    claim: str,
    check: str | None,
) -> SaplingVerdict:
    del policy, evidence, claim, check
    missing = unset_decisions(list(_LIVE_DECISIONS))
    if missing:
        raise DecisionRequired(
            "Live Sapling is refused while these are TODO_HUMAN: "
            + ", ".join(missing)
            + ". No GPU was loaded and no socket was opened."
        )
    hosting = require_decision("sapling.hosting")
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        f"sapling.hosting is {hosting!r}. Every model call has to go through Mubit, "
        "and it is unconfirmed that Mubit can route to a self-hosted Sapling endpoint. "
        "No socket was opened."
    )

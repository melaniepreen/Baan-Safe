"""Pinned latte-bench checkout. The commit is the reference, not a copy."""

from __future__ import annotations

from paths import ROOT

REPO_URL = "https://github.com/MubitLabs/latte-bench"
PIN = "3828bd8c201c272c8eb021608631f2217316ec33"
SUBMODULE = ROOT / "third_party" / "latte-bench"
STUDY_PATH = SUBMODULE / "docs" / "model-study" / "summary.json"
REFERENCE_NAME = "latte-reference.json"

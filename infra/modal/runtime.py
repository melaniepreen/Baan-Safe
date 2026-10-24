"""Modal secrets and volumes. Tokens are names, never values."""

from __future__ import annotations

import modal

from infra.modal.common import (
    HF_CACHE_VOLUME,
    HF_SECRET_NAME,
    MUBIT_SECRET_NAME,
    VERSIONS_VOLUME,
    repo_root,
)

HF_CACHE_PATH = "/root/.cache/huggingface"
VERSIONS_PATH = "/vol"


def hf_secret() -> modal.Secret:
    return modal.Secret.from_name(HF_SECRET_NAME, required_keys=["HF_TOKEN"])


def mubit_secret() -> modal.Secret:
    return modal.Secret.from_name(MUBIT_SECRET_NAME, required_keys=["MUBIT_API_KEY"])


def hf_cache() -> modal.Volume:
    return modal.Volume.from_name(HF_CACHE_VOLUME, create_if_missing=True)


def versions() -> modal.Volume:
    return modal.Volume.from_name(VERSIONS_VOLUME, create_if_missing=True)


def with_repo(image: modal.Image) -> modal.Image:
    decisions = repo_root() / "config" / "decisions.yaml"
    return (
        image.add_local_python_source("infra", "contracts")
        .add_local_file(str(decisions), "/opt/baansafe/config/decisions.yaml")
        .env({"BAANSAFE_DECISIONS": "/opt/baansafe/config/decisions.yaml"})
    )

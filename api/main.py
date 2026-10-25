"""BaanSafe API. `make serve` binds this app on port 8000."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes.endpoints import router
from api.routes.policies import router as policies_router
from api.routes.training import router as training_router
from config.envfile import load_env_file
from memory.adapter import status as memory_status
from paths import ROOT

load_env_file()

_memory = memory_status()
if _memory["dormant"]:
    logging.getLogger("baansafe").warning(_memory["warning"])

app = FastAPI(
    title="BaanSafe",
    version="0.2.0",
    summary=(
        "Flood call-triage. System 1 is rules-only (S1_IMPL=real); System 2 is "
        "Nemotron via Mubit (S2_IMPL=real). Memory is BaanSafe's own store "
        "(MEMORY_IMPL=local). See GET /health."
    ),
)
# Dev-only, so the static transcript player can call the API. Human sign-off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(policies_router)
app.include_router(training_router)
# /ui/training.html reads GET /training. Same static mount as the player and the town.
app.mount("/ui", StaticFiles(directory=ROOT / "ui", html=True), name="ui")

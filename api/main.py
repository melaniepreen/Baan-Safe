"""BaanSafe API. `make serve` binds this app on port 8000."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes.endpoints import router
from paths import ROOT

app = FastAPI(
    title="BaanSafe",
    version="0.1.0",
    summary="Flood call-triage scaffold. System 1 and System 2 logic are not implemented.",
)
# Dev-only, so the static transcript player can call the API. Human sign-off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/ui", StaticFiles(directory=ROOT / "ui", html=True), name="ui")

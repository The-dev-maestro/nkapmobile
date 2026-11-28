"""Endpoint officiel SAFINUM Sandbox Finale (POST /sandbox).

Enregistrez https://<votre-domaine>/sandbox sur https://safinum.cm/api/v1/sandbox/endpoint
pour les canaux `ussd`, `mobile`, `web` (ainsi que `sms`, `atm`, `ivr`).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.sandbox.language import (
    ALLOWED_ORTHOGRAPHIES,
    get_orthography_mode,
    set_orthography_mode,
    translate_ui,
)
from app.sandbox.ussd_flow import handle_channel_turn

router = APIRouter(prefix="/sandbox", tags=["safinum-sandbox"])


@router.get("")
@router.get("/")
async def sandbox_health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "nkap-safinum-middleware",
        "channels": ["ussd", "mobile", "web", "sms", "atm", "ivr"],
        "languages": ["ewo", "dua", "fr", "en"],
        "orthography": get_orthography_mode(),
    }


@router.get("/orthography")
async def get_orthography() -> dict[str, Any]:
    return {"mode": get_orthography_mode(), "allowed": sorted(ALLOWED_ORTHOGRAPHIES)}


@router.post("/orthography")
async def update_orthography(request: Request) -> dict[str, Any]:
    body = await request.json()
    mode = str(body.get("mode") or "").strip().lower()
    if mode not in ALLOWED_ORTHOGRAPHIES:
        raise HTTPException(status_code=400, detail="mode must be 'aglc' or 'intuitive'")
    applied = set_orthography_mode(mode)
    return {"ok": True, "mode": applied}


@router.post("")
@router.post("/")
async def sandbox_gateway(request: Request) -> dict[str, Any]:
    payload = await request.json()
    trace_id = request.headers.get("X-Trace-Id") or payload.get("trace_id")

    if payload.get("type") == "ui_translation":
        return translate_ui(payload)

    return await run_in_threadpool(handle_channel_turn, payload, trace_id)

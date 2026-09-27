"""API router aggregation. Mounted under ``/api/v1`` by ``app.main``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import alerts, assets, auth, geo, live, ops, reports, risk

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(geo.router)
api_router.include_router(risk.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(assets.router)
api_router.include_router(ops.router)
api_router.include_router(live.router)

__all__ = ["api_router"]

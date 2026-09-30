"""FastAPI app: API REST + frontend statico. Nessuna autenticazione in fase 1
(rimandata quando l'app sarà più matura: il binding è memberships.external_subject).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import assets, dashboards, findings, imports, reports, tenants

app = FastAPI(
    title="VCM — Vulnerability & Compliance Management",
    version="0.1.0",
    description=("Piattaforma multi-tenant per vulnerabilità e conformità "
                 "(STIG/SCAP, Active Directory) su infrastruttura sistemistica."),
)

app.include_router(tenants.router)
app.include_router(assets.router)
app.include_router(imports.router)
app.include_router(findings.router)
app.include_router(dashboards.router)
app.include_router(reports.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Frontend statico (SPA leggera in frontend/)
_frontend_dir = os.getenv("FRONTEND_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend"))
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

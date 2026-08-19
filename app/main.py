"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import crud
from .api import router as api_router
from .config import settings
from .database import init_db, session_scope

_SEED_PATH = Path(__file__).parent / "data" / "movable_shapes_seed.json"


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    init_db()
    with session_scope() as session:
        crud.ensure_setlist(session, slug="setlist1", name="Setlist 1")
        crud.seed_movable_shapes_if_empty(session, _SEED_PATH)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)

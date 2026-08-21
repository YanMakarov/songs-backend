"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import crud
from .api import router as api_router
from .auth import sessions as auth_sessions
from .auth.policy import enforce_auth, log_startup_banner
from .config import AuthMode, settings
from .database import init_db, session_scope

_SEED_PATH = Path(__file__).parent / "data" / "movable_shapes_seed.json"

#: How long a soft-deleted song stays restorable.
TRASH_RETENTION_DAYS = 30


#: FastAPI serves the schema and Swagger UI as plain Starlette routes, which
#: application-wide dependencies do not cover — they would stay reachable with
#: everything else closed. It is the API surface rather than the data, but on a
#: deployment that means to be shut there is no reason to publish it.
_docs_open = settings.auth_mode is not AuthMode.REQUIRED

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if _docs_open else None,
    redoc_url="/redoc" if _docs_open else None,
    openapi_url="/openapi.json" if _docs_open else None,
    # Applied to every route on the app, including any router added later:
    # a new endpoint is closed until app/auth/policy.py says otherwise.
    dependencies=[Depends(enforce_auth)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Response headers are hidden from cross-origin JS unless listed here, and
    # the frontend needs the version to send it back as If-Match.
    expose_headers=["ETag", "X-Deleted", "X-Merged", "X-Overwritten-Fields"],
)


@app.on_event("startup")
def _on_startup() -> None:
    init_db()
    log_startup_banner()
    with session_scope() as session:
        setlist = crud.ensure_setlist(session, slug="setlist1", name="Setlist 1")
        crud.seed_movable_shapes_if_empty(session, _SEED_PATH)
        crud.purge_deleted(session, setlist, older_than_days=TRASH_RETENTION_DAYS)
        auth_sessions.purge_expired(session)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness, plus how protected this deployment currently is.

    Reporting the mode gives away nothing an unauthenticated request could not
    work out by trying one endpoint, and it turns "why is production open?"
    into a single curl instead of an ssh session.
    """

    return {"status": "ok", "auth": settings.auth_mode.value}


app.include_router(api_router)

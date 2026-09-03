"""FastAPI application entrypoint.

The app layer, and the only place that knows the full list of modules: it
mounts their routers and runs their startup hooks. Nothing here reaches into a
module past its front door, which is why this file says nothing about setlists,
seed files or session tables.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import AuthMode, settings
from .core.database import session_scope
from .modules import auth, pdf, shapes, songs
from .tables import init_database

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
    # a new endpoint is closed until auth's policy says otherwise.
    dependencies=[Depends(auth.enforce_auth)],
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
    init_database()
    auth.log_startup_banner()
    with session_scope() as session:
        songs.on_startup(session)
        shapes.seed_if_empty(session)
        auth.purge_expired(session)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness, plus how protected this deployment currently is.

    Reporting the mode gives away nothing an unauthenticated request could not
    work out by trying one endpoint, and it turns "why is production open?"
    into a single curl instead of an ssh session.
    """

    return {"status": "ok", "auth": settings.auth_mode.value}


# Auth first so that signing in is reachable before anything that needs a
# session; the rest in no particular order — their prefixes do not overlap.
app.include_router(auth.router)
app.include_router(songs.router)
app.include_router(pdf.router)
app.include_router(shapes.router)

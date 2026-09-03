"""Every table in the application, in one place.

SQLModel registers a table on `SQLModel.metadata` when its class is first
defined, so `create_all` only ever creates tables whose module has been
imported. While every model lived in one file that was guaranteed by accident.
Now that each module owns its own tables, this file is the guarantee — and
`init_database` exists so a caller cannot satisfy the import checker by
deleting the import it depends on.

Adding a module with tables means adding it here. Forgetting shows up as a
missing table on a fresh database, not on an existing one, which is exactly
the kind of bug that reaches production.
"""

from __future__ import annotations

from .core.database import init_db
from .modules.auth import models as auth_models  # noqa: F401
from .modules.shapes import models as shape_models  # noqa: F401
from .modules.songs import models as song_models  # noqa: F401


def init_database() -> None:
    """Create missing tables, then bring existing ones up to date."""

    init_db()

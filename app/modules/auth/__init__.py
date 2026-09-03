"""Authentication: accounts, sessions, the access policy, and the routes
behind them.

`get_author` is exported alongside the policy because writes elsewhere need a
name to record and should not have to know that a name comes from a session
cookie. `purge_expired` is the module's startup hook.
"""

from .authorship import get_author
from .policy import current_user, enforce_auth, log_startup_banner, require_user
from .routes import router
from .sessions import purge_expired

__all__ = [
    "current_user",
    "enforce_auth",
    "get_author",
    "log_startup_banner",
    "purge_expired",
    "require_user",
    "router",
]

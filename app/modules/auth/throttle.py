"""Rate limiting for sign-in attempts.

A dict in process memory, which is enough because the backend runs as a single
uvicorn process with no `--workers` (see scripts/run-backend.sh). Two
consequences worth knowing: the counters reset on restart, and the day this
deployment grows a second worker they stop being global. At that point this
module moves to a table; the interface is meant to survive that.

Attempts are counted per (username, client IP) so that one person fumbling a
password cannot lock out the band, and a single IP cannot walk the user list.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

#: Failures allowed before the pause starts.
FREE_ATTEMPTS = 5
#: The pause doubles per failure past the allowance, up to this.
MAX_LOCKOUT_SECONDS = 15 * 60
#: Counters idle for this long are dropped, so the dict cannot grow forever.
FORGET_AFTER_SECONDS = 60 * 60


@dataclass
class _Counter:
    failures: int = 0
    blocked_until: float = 0.0
    touched_at: float = field(default_factory=time.monotonic)


_counters: dict[tuple[str, str], _Counter] = {}


def _key(username: str, client_ip: str) -> tuple[str, str]:
    return (username.strip().lower(), client_ip or "-")


def _prune(now: float) -> None:
    stale = [k for k, c in _counters.items() if now - c.touched_at > FORGET_AFTER_SECONDS]
    for k in stale:
        del _counters[k]


def retry_after(username: str, client_ip: str) -> int:
    """Seconds the caller must wait, or 0 if they may try now."""

    now = time.monotonic()
    _prune(now)
    counter = _counters.get(_key(username, client_ip))
    if not counter:
        return 0
    remaining = counter.blocked_until - now
    return int(remaining) + 1 if remaining > 0 else 0


def record_failure(username: str, client_ip: str) -> None:
    now = time.monotonic()
    counter = _counters.setdefault(_key(username, client_ip), _Counter())
    counter.failures += 1
    counter.touched_at = now
    if counter.failures > FREE_ATTEMPTS:
        penalty = min(2 ** (counter.failures - FREE_ATTEMPTS), MAX_LOCKOUT_SECONDS)
        counter.blocked_until = now + penalty


def record_success(username: str, client_ip: str) -> None:
    _counters.pop(_key(username, client_ip), None)


def reset() -> None:
    """Drop every counter. For tests."""

    _counters.clear()

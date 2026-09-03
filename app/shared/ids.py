"""Public identifiers for rows that appear in URLs.

Random-then-timestamp rather than a UUID: the id ends up in every song URL and
in the write queue the frontend keeps on disk, so it is worth keeping short
enough to read out loud. The timestamp half keeps ids roughly ordered by
creation, which makes a table dump legible; the random half is what actually
prevents collisions.
"""

from __future__ import annotations

import secrets
import time


def generate_public_id() -> str:
    random_part = format(secrets.randbits(32), "x")
    timestamp_part = format(int(time.time() * 1000), "x")
    return (random_part + timestamp_part)[:20]

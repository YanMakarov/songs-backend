"""The movable chord-shape library.

A shape is a fretting pattern with no root of its own — slide it up the neck
and it names a different chord. The module owns the stored patterns; working
out which notes a shape produces at a given fret is the frontend's job, and
deliberately not stored.

Nothing else in the backend depends on shapes: no foreign key points here, and
the seeding hook is the only thing the app layer needs.
"""

from .routes import router
from .service import seed_if_empty

__all__ = ["router", "seed_if_empty"]

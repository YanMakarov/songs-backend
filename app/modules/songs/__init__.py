"""Songs: the setlist, the songs in it, and the versioning that lets several
people edit them at once.

The module is deliberately one aggregate rather than two. A song's `rev` comes
from a counter on its setlist, and the change feed the frontend polls is a
setlist-wide read over songs — split into separate modules, the two would
depend on each other in both directions.

`SongLine` is published because a line is the unit other modules speak in: the
PDF importer produces lines, and does not otherwise need to know what a song
is. The service functions are not published — a caller outside this module
that needs to write a song should be going through the HTTP surface.
"""

from .bootstrap import on_startup
from .routes import router
from .schemas import SongChord, SongLine

__all__ = ["SongChord", "SongLine", "on_startup", "router"]

"""Importing a song from a PDF.

Stateless: the endpoint parses an upload and hands back song lines the client
can save (or discard) as a normal write. Nothing is stored here, which is why
the module has no models and no service — just the parser and one route.

It depends on `songs` for the shape of a line, and on `shared.music` for the
chord recognition that decides which of them are chord lines.
"""

from .routes import router

__all__ = ["router"]

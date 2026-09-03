"""Feature modules.

Each subpackage owns one area end to end — its tables, its schemas, its
service functions and its routes — and publishes a deliberately small surface
from its `__init__.py`. Reaching past that front door (`modules.songs.service`
from outside `songs`) is what the import contracts in pyproject.toml forbid:
the boundary is only real while nothing crosses it by file path.
"""

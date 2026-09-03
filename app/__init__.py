"""Songs backend.

Layers, from the bottom up — the arrows only point one way, and the import
contracts in pyproject.toml are what keep it that way:

    app  ->  modules  ->  core  ->  shared

`shared` is self-contained helpers, `core` is configuration and the database,
`modules` are the features, and this layer wires them together. A module may
use another module, but only through its `__init__.py`.
"""

from .main import app  # noqa: F401

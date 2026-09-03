"""The bottom layer: self-contained helpers that know nothing about this app.

Nothing here may import from `core`, `modules` or the app itself. That is what
makes these modules safe to use from anywhere — and it is checked, not merely
intended: see the `songs-shared` contract in pyproject.toml.
"""

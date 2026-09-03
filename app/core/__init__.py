"""Infrastructure every module is allowed to depend on: configuration, the
database engine, and the conventions the HTTP surface is built from.

`core` may use `shared`. It must not know about any feature module — a module
name appearing in an import here means the dependency arrow has been turned
around.
"""

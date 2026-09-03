"""The base every API payload is built on.

One convention, applied in one place: Python stays snake_case, the wire stays
camelCase. `populate_by_name` keeps both spellings accepted on the way in, so
a payload written by hand in snake_case still validates, and `from_attributes`
lets a schema be built straight from an ORM row.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

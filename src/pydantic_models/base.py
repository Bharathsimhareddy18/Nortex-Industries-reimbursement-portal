"""Shared base for every response model."""
from pydantic import BaseModel, ConfigDict


class RowModel(BaseModel):
    """A response model built straight from a database row (an SQLAlchemy object), not from a dict."""

    model_config = ConfigDict(from_attributes=True)

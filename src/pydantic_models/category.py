"""The categories table, as the API shows it."""
from src.pydantic_models.base import RowModel


class CategoryOut(RowModel):
    id: int
    name: str
    config: dict  # that category's rules

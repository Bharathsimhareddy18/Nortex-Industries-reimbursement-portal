"""Templates (Travelling, Food, Hotel stay) and the fields each one asks for."""
from typing import Literal

from pydantic import BaseModel


class TemplateOut(BaseModel):
    template_id: int
    template_name: str


class FieldOut(BaseModel):
    name: str  # the key to use in create_claim
    label: str  # what the form shows
    type: Literal["text", "integer", "money", "datetime", "boolean", "choice", "longtext"]
    required: bool
    choices: list[str | int] | None = None  # for type 'choice'
    min: float | None = None  # smallest allowed number
    default: str | int | float | bool | None = None  # used when an optional field is left out


class TemplateFieldsOut(BaseModel):
    template_id: int
    template_name: str
    fields: list[FieldOut]

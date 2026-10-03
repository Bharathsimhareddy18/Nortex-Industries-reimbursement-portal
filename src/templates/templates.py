"""The claim templates (Travelling, Food, Hotel stay): listing them, describing their fields, checking what a user submits."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, ValidationError, create_model
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Category
from src.errors import AppError


class Templates:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Category]:
        """Every template, for the 'what do you want to claim?' screen."""
        return list(self.db.scalars(select(Category).order_by(Category.id)))

    def get(self, template_id: int) -> Category:
        """One template by id, or a 404."""
        template = self.db.get(Category, template_id)
        if template is None:
            raise AppError(404, "No template with this id")
        return template

    def required_fields(self, template_id: int, template_name: str) -> Category:
        """The template, but only if the id AND the name both match; the screen uses its fields to draw the form."""
        template = self.get(template_id)
        if template.name.lower() != template_name.strip().lower():
            raise AppError(404, "The template id and name do not match")
        return template

    def clean_fields(self, template: Category, fields: dict) -> dict:
        """Check what the user submitted against the template: required fields present, right types, no unknown fields.

        Returns the cleaned values (numbers, dates and so on in a JSON-safe form), ready to store on the claim.
        """
        return self.clean_step(template.config["fields"], fields, template.name)

    def clean_step(self, field_defs: list[dict], fields: dict, name: str) -> dict:
        """The same check for one form: the template's own fields, or one form step of an admin-built flow."""
        try:
            return self._build_model(name, field_defs)(**fields).model_dump(mode="json")
        except ValidationError as error:
            problems = [f"{'.'.join(str(p) for p in e['loc']) or 'fields'}: {e['msg']}" for e in error.errors()]
            raise AppError(422, "Some fields are missing or invalid", problems)

    def _build_model(self, name: str, field_defs: list[dict]):
        """Turn a field list into a Pydantic model, so Pydantic does the checking."""
        definitions = {}
        for field in field_defs:
            annotation = self._annotation(field)
            definitions[field["name"]] = (annotation, ... if field["required"] else field.get("default"))
        return create_model(name.replace(" ", ""), __config__=ConfigDict(extra="forbid"), **definitions)

    def _annotation(self, field: dict):
        """The Python type (with limits) for one field type."""
        kind, minimum = field["type"], field.get("min", 0)
        if kind == "text":
            return Annotated[str, Field(min_length=1)]
        if kind == "longtext":  # a paragraph; "min" is the least number of characters (so "ok" is not an answer to "why?")
            return Annotated[str, Field(min_length=int(field.get("min", 1)), max_length=1000)]
        if kind == "integer":
            return Annotated[int, Field(ge=minimum)]
        if kind == "money":
            return Annotated[Decimal, Field(ge=Decimal(str(minimum)), max_digits=12, decimal_places=2)]
        if kind == "datetime":
            return datetime
        if kind == "boolean":
            return bool
        return Literal[tuple(field["choices"])]  # kind == "choice"

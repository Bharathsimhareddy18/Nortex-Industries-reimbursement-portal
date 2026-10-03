"""Admin-built flows: the blocks an admin can drop into a template, and how a flow is shown to the screens."""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.pydantic_models.receipt import Head
from src.pydantic_models.template import FieldOut

FieldType = Literal["text", "integer", "money", "datetime", "boolean", "choice", "longtext"]


class FlowField(BaseModel):
    """One question on a form step. `name` is the key the answer is stored under, so it must be a plain lower-case word."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=100)
    type: FieldType
    required: bool = True
    choices: list[str] | None = None
    min: float | None = None

    @field_validator("name")
    @classmethod
    def not_reserved(cls, name: str) -> str:
        if name.startswith("model_"):
            raise ValueError("this name is reserved")
        return name

    @model_validator(mode="after")
    def choices_only_for_choice(self):
        if self.type == "choice":
            clean = [c.strip() for c in (self.choices or []) if c.strip()]
            if len(clean) < 2 or len(set(clean)) != len(clean):
                raise ValueError(f"'{self.label}' needs at least two different choices")
            self.choices = clean
        else:
            self.choices = None
        return self


class Approver(BaseModel):
    """Who acts on a step: a named person, or whoever is the claimant's Reporting Manager."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["user", "reporting_manager"]
    emp_code: str | None = None

    @model_validator(mode="after")
    def user_needs_a_person(self):
        if self.mode == "user" and not self.emp_code:
            raise ValueError("choose a person")
        if self.mode != "user":
            self.emp_code = None
        return self


class FormStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["form"]
    title: str = Field(min_length=1, max_length=100)
    fields: list[FlowField] = Field(min_length=1)


class ApprovalStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["approval"]
    approver: Approver


class AdvanceStep(BaseModel):
    """Finance releases an advance; `amount_field` names the money field the employee typed it into."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["advance"]
    approver: Approver
    amount_field: str


class UploadBillsStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["upload_bills"]
    heads: list[Head] = Field(min_length=1)


class FinanceReviewStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["finance_review"]
    approver: Approver


class PayoutStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    type: Literal["payout"]
    approver: Approver


Step = Annotated[Union[FormStep, ApprovalStep, AdvanceStep, UploadBillsStep, FinanceReviewStep, PayoutStep], Field(discriminator="type")]


class FlowIn(BaseModel):
    """What the builder sends to create or change a template."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=100)
    estimate_field: str | None = None  # a money field whose answer is the claim's estimated amount (optional)
    steps: list[Step] = Field(min_length=2)


class AdminTemplateOut(BaseModel):
    id: int
    name: str
    kind: Literal["fixed", "flow"]
    fields: list[FieldOut] | None = None  # fixed templates: their form
    flow: dict | None = None  # flow templates: {"estimate_field", "steps": [...]}

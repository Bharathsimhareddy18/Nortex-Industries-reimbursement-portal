"""Templates: what can be claimed, and what each one asks for."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.database.db import get_db
from src.database.models import Employee
from src.pydantic_models.template import TemplateFieldsOut, TemplateOut
from src.templates.templates import Templates

router = APIRouter(tags=["templates"])


@router.get("/get_templates", response_model=list[TemplateOut])
def get_templates(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """The 'what do you want to claim?' list: every template's id and name."""
    return [TemplateOut(template_id=t.id, template_name=t.name) for t in Templates(db).list_all()]


@router.get("/get_template_required_fields", response_model=TemplateFieldsOut)
def get_template_required_fields(
    template_id: int, template_name: str, user: Employee = Depends(current_user), db: Session = Depends(get_db)
):
    """The fields to show on the form for one template. The id and the name must both match, otherwise 404."""
    template = Templates(db).required_fields(template_id, template_name)
    return TemplateFieldsOut(template_id=template.id, template_name=template.name, fields=template.config["fields"])

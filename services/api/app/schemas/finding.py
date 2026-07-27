"""Response schema for findings."""

import uuid

from pydantic import BaseModel, ConfigDict

from app.enums import ModuleKey, Priority, Severity


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_id: uuid.UUID | None
    module: ModuleKey
    rule: str
    severity: Severity
    priority: Priority | None
    title: str
    detail: str | None
    selector: str | None
    snippet: str | None
    recommendation: dict
    meta: dict

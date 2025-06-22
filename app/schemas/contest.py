from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.problem import ProblemMinimal


class ContestBase(BaseModel):
    id: str
    title: str
    description_md: Optional[str] = None
    start_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    allow_upsolving: bool = True

    model_config = ConfigDict(from_attributes=True)


class Contest(ContestBase):
    problems: List[ProblemMinimal] = []


class ContestMinimal(BaseModel):
    id: str
    title: str
    start_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

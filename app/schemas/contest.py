from typing import List, Optional

from pydantic import BaseModel

from app.schemas.problem import ProblemMinimal


class ContestBase(BaseModel):
    id: str
    title: str
    description_md: Optional[str] = None


class Contest(ContestBase):
    problems: List[ProblemMinimal] = []


class ContestMinimal(BaseModel):
    id: str
    title: str

from typing import List, Optional

from pydantic import BaseModel


class TestCase(BaseModel):
    name: str
    input_content: Optional[str] = None
    output_content: Optional[str] = None


class ProblemBase(BaseModel):
    id: str
    title: str
    description_md: str
    time_limit_sec: int
    memory_limit_mb: int
    allowed_languages: List[str]


class Problem(ProblemBase):
    test_cases: List[TestCase] = []


class ProblemMinimal(BaseModel):
    id: str
    title: str

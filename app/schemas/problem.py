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
    generator_code: Optional[str] = None

    generator_time_limit_sec: Optional[float] = None
    generator_memory_limit_mb: Optional[int] = None

    submission_cooldown_sec: Optional[int] = None
    generator_cooldown_sec: Optional[int] = None


class Problem(ProblemBase):
    test_cases: List[TestCase] = []


class ProblemMinimal(BaseModel):
    id: str
    title: str

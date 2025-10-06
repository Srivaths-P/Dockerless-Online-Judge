from typing import List, Optional

from pydantic import BaseModel


class TestCase(BaseModel):
    name: str
    input_content: Optional[str] = None
    output_content: Optional[str] = None


class ProblemPublic(BaseModel):
    id: str
    title: str
    description_md: str
    time_limit_sec: int
    memory_limit_mb: int
    allowed_languages: List[str]
    generator_available: bool
    public_test_cases: List[TestCase] = []
    submission_cooldown_sec: Optional[int] = None
    generator_cooldown_sec: Optional[int] = None


class Problem(BaseModel):
    id: str
    title: str
    description_md: str
    time_limit_sec: int
    memory_limit_mb: int
    allowed_languages: List[str]

    public_test_cases: List[TestCase] = []
    private_test_cases: List[TestCase] = []
    validator_type: str = "diff"
    validator_code: Optional[str] = None
    validator_language: str = "python"
    validator_time_limit_sec: int = 10
    validator_memory_limit_mb: int = 256

    generator_code: Optional[str] = None
    generator_language: str = "python"
    generator_time_limit_sec: Optional[float] = None
    generator_memory_limit_mb: Optional[int] = None

    submission_cooldown_sec: Optional[int] = None
    generator_cooldown_sec: Optional[int] = None


class ProblemMinimal(BaseModel):
    id: str
    title: str

from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class SubmissionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TestCaseResult(BaseModel):
    test_case_name: str
    status: SubmissionStatus
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time_ms: Optional[float] = None
    memory_used_kb: Optional[int] = None


class SubmissionBase(BaseModel):
    problem_id: str
    contest_id: str
    language: str
    code: str


class SubmissionCreate(SubmissionBase):
    pass


class SubmissionUpdate(BaseModel):
    status: Optional[SubmissionStatus] = None
    results: Optional[List[TestCaseResult]] = None


class SubmissionInDBBase(SubmissionBase):
    id: str
    submitter_id: int
    status: SubmissionStatus
    submitted_at: datetime
    results: List[TestCaseResult] = []
    user_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Submission(SubmissionInDBBase):
    pass


class SubmissionInDB(SubmissionInDBBase):
    results_json: Optional[str] = None


class SubmissionInfo(BaseModel):
    id: str
    problem_id: str
    contest_id: str
    user_email: Optional[str] = None
    language: str
    status: SubmissionStatus
    submitted_at: datetime

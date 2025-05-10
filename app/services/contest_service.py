import uuid
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


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


class SubmissionCreate(BaseModel):
    problem_id: str
    contest_id: str
    language: str
    code: str


class Submission(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    problem_id: str
    contest_id: str
    language: str
    code: str

    user_email: str
    status: SubmissionStatus = SubmissionStatus.PENDING
    results: List[TestCaseResult] = []
    submitted_at: str


class SubmissionInfo(BaseModel):
    id: uuid.UUID
    problem_id: str
    contest_id: str
    user_email: str
    status: SubmissionStatus
    submitted_at: str


import os
import json
from typing import List, Dict, Optional
from app.schemas.contest import Contest, ContestMinimal
from app.schemas.problem import Problem, ProblemMinimal, TestCase

SERVER_DATA_PATH = "server_data"
CONTESTS_PATH = os.path.join(SERVER_DATA_PATH, "contests")

_contests_db: Dict[str, Contest] = {}


def _load_problem(contest_id: str, problem_id: str, problem_path: str) -> Optional[Problem]:
    index_md_path = os.path.join(problem_path, "index.md")
    settings_json_path = os.path.join(problem_path, "settings.json")

    if not (os.path.exists(index_md_path) and os.path.exists(settings_json_path)):
        return None

    with open(index_md_path, "r") as f:
        description_md = f.read()
    with open(settings_json_path, "r") as f:
        settings_data = json.load(f)

    test_cases_data = []
    for item in os.listdir(problem_path):
        if item.endswith(".in"):
            name = item[:-3]
            in_path = os.path.join(problem_path, item)
            out_path = os.path.join(problem_path, f"{name}.out")

            tc_input = None
            tc_output = None
            if os.path.exists(in_path):
                with open(in_path, "r") as f_in:
                    tc_input = f_in.read()
            if os.path.exists(out_path):
                with open(out_path, "r") as f_out:
                    tc_output = f_out.read()

            test_cases_data.append(TestCase(name=name, input_content=tc_input, output_content=tc_output))

    return Problem(
        id=problem_id,
        title=settings_data.get("title", problem_id),
        description_md=description_md,
        time_limit_sec=settings_data.get("time_limit_sec", 2),
        memory_limit_mb=settings_data.get("memory_limit_mb", 64),
        allowed_languages=settings_data.get("allowed_languages", ["python", "cpp"]),
        test_cases=test_cases_data
    )


def load_contests_on_startup():
    global _contests_db
    _contests_db = {}
    if not os.path.exists(CONTESTS_PATH):
        print(f"Warning: Contests directory not found at {CONTESTS_PATH}")
        return

    for contest_id in os.listdir(CONTESTS_PATH):
        contest_path = os.path.join(CONTESTS_PATH, contest_id)
        if not os.path.isdir(contest_path):
            continue

        index_md_path = os.path.join(contest_path, "index.md")
        settings_json_path = os.path.join(contest_path, "settings.json")

        description_md = ""
        if os.path.exists(index_md_path):
            with open(index_md_path, "r") as f:
                description_md = f.read()

        settings_data = {}
        if os.path.exists(settings_json_path):
            with open(settings_json_path, "r") as f:
                settings_data = json.load(f)

        problems_in_contest: List[ProblemMinimal] = []
        parsed_problems_in_contest: List[Problem] = []

        for item_name in os.listdir(contest_path):
            item_path = os.path.join(contest_path, item_name)
            if os.path.isdir(item_path):

                problem = _load_problem(contest_id, item_name, item_path)
                if problem:
                    problems_in_contest.append(ProblemMinimal(id=problem.id, title=problem.title))
                    parsed_problems_in_contest.append(problem)

        _contests_db[contest_id] = Contest(
            id=contest_id,
            title=settings_data.get("title", contest_id),
            description_md=description_md,
            problems=problems_in_contest
        )

        _contests_db[contest_id]._full_problems = {p.id: p for p in parsed_problems_in_contest}


def get_all_contests() -> List[ContestMinimal]:
    return [ContestMinimal(id=c.id, title=c.title) for c in _contests_db.values()]


def get_contest_by_id(contest_id: str) -> Optional[Contest]:
    return _contests_db.get(contest_id)


def get_problem_by_id(contest_id: str, problem_id: str) -> Optional[Problem]:
    contest = _contests_db.get(contest_id)
    if contest and hasattr(contest, '_full_problems'):
        return contest._full_problems.get(problem_id)
    return None

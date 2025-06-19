import json
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from fastapi import HTTPException, status
from app.schemas.contest import Contest, ContestMinimal
from app.schemas.problem import Problem, ProblemMinimal, TestCase

SERVER_DATA_PATH = "server_data"
CONTESTS_PATH = os.path.join(SERVER_DATA_PATH, "contests")

_contests_db: Dict[str, Contest] = {}


def _parse_settings_data(settings_data: Dict) -> Dict:
    parsed_settings = {}
    for key, value in settings_data.items():
        if key == 'start_time' and isinstance(value, str):
            try:
                parsed_settings[key] = datetime.fromisoformat(value)
                if parsed_settings[key].tzinfo is None:
                    parsed_settings[key] = parsed_settings[key].replace(tzinfo=timezone.utc)
            except ValueError:
                print(f"Warning: Could not parse start_time '{value}' as ISO 8601 datetime.")
                parsed_settings[key] = None
        elif key in ['time_limit_sec', 'memory_limit_mb', 'generator_memory_limit_mb', 'submission_cooldown_sec',
                     'generator_cooldown_sec'] and value is not None:
            try:
                parsed_settings[key] = int(value)
            except (ValueError, TypeError):
                print(f"Warning: Invalid integer value for {key}: {value}. Using default or None.")
                parsed_settings[key] = None
        elif key == 'generator_time_limit_sec' and value is not None:
            try:
                parsed_settings[key] = float(value)
            except (ValueError, TypeError):
                print(f"Warning: Invalid float value for {key}: {value}. Using default or None.")
                parsed_settings[key] = None
        else:
            parsed_settings[key] = value
    return parsed_settings


def _load_problem(contest_id: str, problem_id: str, problem_path: str) -> Optional[Problem]:
    index_md_path = os.path.join(problem_path, "index.md")
    settings_json_path = os.path.join(problem_path, "settings.json")
    generator_py_path = os.path.join(problem_path, "generator.py")

    if not (os.path.exists(index_md_path) and os.path.exists(settings_json_path)):
        print(f"Warning: Missing index.md or settings.json for problem {problem_id} in contest {contest_id}")
        return None

    description_md = ""
    settings_data_raw = {}
    generator_code = None

    try:
        with open(index_md_path, "r", encoding='utf-8') as f:
            description_md = f.read()
        with open(settings_json_path, "r", encoding='utf-8') as f:
            settings_data_raw = json.load(f)
        if os.path.exists(generator_py_path):
            with open(generator_py_path, "r", encoding='utf-8') as f:
                generator_code = f.read()
    except FileNotFoundError:
        print(f"Error: File not found during loading of problem {problem_id} in contest {contest_id}.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in settings for problem {problem_id} in contest {contest_id}.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred loading problem {problem_id} base files: {e}")
        return None

    settings_data = _parse_settings_data(settings_data_raw)

    test_cases_data: List[TestCase] = []
    for item in os.listdir(problem_path):
        if item.endswith(".in"):
            name = item[:-3]
            in_path = os.path.join(problem_path, item)
            out_path = os.path.join(problem_path, f"{name}.out")

            tc_input = None
            tc_output = None
            try:
                if os.path.exists(in_path):
                    with open(in_path, "r", encoding='utf-8') as f_in:
                        tc_input = f_in.read()
                if os.path.exists(out_path):
                    with open(out_path, "r", encoding='utf-8') as f_out:
                        tc_output = f_out.read()
                test_cases_data.append(TestCase(name=name, input_content=tc_input, output_content=tc_output))
            except Exception as e:
                print(f"Error loading test case {name} for problem {problem_id}: {e}")

    return Problem(
        id=problem_id,
        title=settings_data.get("title", problem_id),
        description_md=description_md,
        time_limit_sec=settings_data.get("time_limit_sec", 2),
        memory_limit_mb=settings_data.get("memory_limit_mb", 64),
        allowed_languages=settings_data.get("allowed_languages", ["python", "c++"]),
        generator_code=generator_code,
        test_cases=test_cases_data,
        generator_time_limit_sec=settings_data.get("generator_time_limit_sec"),
        generator_memory_limit_mb=settings_data.get("generator_memory_limit_mb"),
        submission_cooldown_sec=settings_data.get("submission_cooldown_sec"),
        generator_cooldown_sec=settings_data.get("generator_cooldown_sec")
    )


def load_server_data():
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
            try:
                with open(index_md_path, "r", encoding='utf-8') as f:
                    description_md = f.read()
            except Exception as e:
                print(f"Error reading contest description for {contest_id}: {e}")

        settings_data_raw = {}
        if os.path.exists(settings_json_path):
            try:
                with open(settings_json_path, "r", encoding='utf-8') as f:
                    settings_data_raw = json.load(f)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON in settings for contest {contest_id}.")
            except Exception as e:
                print(f"Error reading contest settings for {contest_id}: {e}")

        parsed_settings = _parse_settings_data(settings_data_raw)

        problems_in_contest_minimal: List[ProblemMinimal] = []
        parsed_problems_in_contest_full: List[Problem] = []

        for item_name in os.listdir(contest_path):
            item_path = os.path.join(contest_path, item_name)
            if os.path.isdir(item_path) and item_name not in ('__pycache__',):
                problem = _load_problem(contest_id, item_name, item_path)
                if problem:
                    problems_in_contest_minimal.append(ProblemMinimal(id=problem.id, title=problem.title))
                    parsed_problems_in_contest_full.append(problem)

        contest_obj = Contest(
            id=contest_id,
            title=parsed_settings.get("title", contest_id),
            description_md=description_md,
            start_time=parsed_settings.get("start_time"),
            duration_minutes=parsed_settings.get("duration_minutes"),
            problems=problems_in_contest_minimal
        )

        setattr(contest_obj, '_full_problems', {p.id: p for p in parsed_problems_in_contest_full})
        _contests_db[contest_id] = contest_obj
    print(f"Loaded {len(_contests_db)} contests.")


def get_all_contests() -> List[ContestMinimal]:
    return [
        ContestMinimal(
            id=c.id,
            title=c.title,
            start_time=c.start_time,
            duration_minutes=c.duration_minutes
        ) for c in _contests_db.values()
    ]


def get_contest_by_id(contest_id: str) -> Optional[Contest]:
    return _contests_db.get(contest_id)


def get_problem_by_id(contest_id: str, problem_id: str) -> Optional[Problem]:
    contest = _contests_db.get(contest_id)
    if contest and hasattr(contest, '_full_problems'):
        return getattr(contest, '_full_problems').get(problem_id)
    return None


def get_contest_status(contest: ContestMinimal) -> str:
    now = datetime.now(timezone.utc)
    if contest.start_time:
        if now < contest.start_time:
            return "Upcoming"
        if contest.duration_minutes is not None:
            end_time = contest.start_time + timedelta(minutes=contest.duration_minutes)
            if now >= contest.start_time and now < end_time:
                return "Active"
            elif now >= end_time:
                return "Ended"
        else:
            return "Active"
    return "Active"


def check_contest_access_and_get_problem(
        contest_id: str, problem_id: str, allow_ended: bool = True
) -> Problem:
    contest = get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    problem = get_problem_by_id(contest_id, problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")

    contest_status = get_contest_status(contest)

    if contest_status == "Upcoming":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contest has not started yet.")

    if contest_status == "Ended" and not allow_ended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contest has ended.")

    return problem

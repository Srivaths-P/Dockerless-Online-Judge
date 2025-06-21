import json
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from fastapi import HTTPException, status

from app.sandbox.common import LANGUAGE_CONFIG
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
                     'generator_cooldown_sec', 'validator_memory_limit_mb',
                     'validator_time_limit_sec'] and value is not None:
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
        elif key == 'allow_upsolving' and isinstance(value, bool):
            parsed_settings[key] = value
        else:
            parsed_settings[key] = value
    return parsed_settings


def _load_problem(contest_id: str, problem_id: str, problem_path: str) -> Optional[Problem]:
    index_md_path = os.path.join(problem_path, "index.md")
    settings_json_path = os.path.join(problem_path, "settings.json")

    if not (os.path.exists(index_md_path) and os.path.exists(settings_json_path)):
        return None

    try:
        with open(index_md_path, "r", encoding='utf-8') as f:
            description_md = f.read()
        with open(settings_json_path, "r", encoding='utf-8') as f:
            settings_data_raw = json.load(f)
    except Exception as e:
        print(f"An unexpected error occurred loading problem {problem_id} base files: {e}")
        return None

    settings_data = _parse_settings_data(settings_data_raw)

    generator_lang = settings_data.get("generator_language", "python").lower()
    validator_lang = settings_data.get("validator_language", "python").lower()

    generator_ext = LANGUAGE_CONFIG.get(generator_lang, {}).get("ext")
    validator_ext = LANGUAGE_CONFIG.get(validator_lang, {}).get("ext")

    generator_code = None
    if generator_ext:
        generator_path = os.path.join(problem_path, f"generator{generator_ext}")
        if os.path.exists(generator_path):
            with open(generator_path, "r", encoding='utf-8') as f:
                gen_code_content = f.read().strip()
                if gen_code_content:
                    generator_code = gen_code_content

    validator_code = None
    if validator_ext:
        validator_path = os.path.join(problem_path, f"validator{validator_ext}")
        if os.path.exists(validator_path):
            with open(validator_path, "r", encoding='utf-8') as f:
                val_code_content = f.read().strip()
                if val_code_content:
                    validator_code = val_code_content

    test_cases_data: List[TestCase] = []
    tests_dir_path = os.path.join(problem_path, "tests")

    search_path = tests_dir_path if os.path.isdir(tests_dir_path) else problem_path

    for item in os.listdir(search_path):
        if item.endswith(".in"):
            name = item[:-3]
            in_path = os.path.join(search_path, item)
            out_path = os.path.join(search_path, f"{name}.out")

            tc_input, tc_output = None, None
            try:
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
        validator_type="custom" if validator_code else "diff",
        validator_code=validator_code,
        validator_language=validator_lang,
        validator_time_limit_sec=settings_data.get("validator_time_limit_sec", 10),
        validator_memory_limit_mb=settings_data.get("validator_memory_limit_mb", 256),
        generator_code=generator_code,
        generator_language=generator_lang,
        generator_time_limit_sec=settings_data.get("generator_time_limit_sec"),
        generator_memory_limit_mb=settings_data.get("generator_memory_limit_mb"),
        test_cases=test_cases_data,
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
            if os.path.isdir(item_path) and not item_name.startswith('__'):
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
            problems=problems_in_contest_minimal,
            allow_upsolving=parsed_settings.get("allow_upsolving", True)
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


def get_contest_status_details(contest: ContestMinimal) -> (str, str):
    now = datetime.now(timezone.utc)
    if not contest.start_time:
        return "Active", "Active"

    def format_timedelta(td: timedelta, prefix: str) -> str:
        seconds = int(td.total_seconds())

        days = seconds // 86400
        if days > 365:
            years = days // 365
            return f"{prefix} in ~{years} year(s)"
        if days > 1:
            hours = (seconds % 86400) // 3600
            return f"{prefix} in {days}d {hours}h"

        hours = seconds // 3600
        if hours > 0:
            minutes = (seconds % 3600) // 60
            return f"{prefix} in {hours}h {minutes}m"

        minutes = seconds // 60
        if minutes > 0:
            secs = seconds % 60
            return f"{prefix} in {minutes}m {secs}s"

        return f"{prefix} in {seconds}s"

    if now < contest.start_time:
        return "Upcoming", format_timedelta(contest.start_time - now, "Starts")

    if contest.duration_minutes is not None:
        end_time = contest.start_time + timedelta(minutes=contest.duration_minutes)
        if now < end_time:
            return "Active", format_timedelta(end_time - now, "Ends")
        else:
            return "Ended", "Ended"

    return "Active", "Active"


def get_contest_category(contest: ContestMinimal) -> str:
    category, _ = get_contest_status_details(contest)
    return category


def get_contest_problem(
        contest_id: str, problem_id: str
) -> Problem:
    contest = get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    contest_category = get_contest_category(contest)

    if contest_category == "Upcoming":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contest has not started yet.")

    problem = get_problem_by_id(contest_id, problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")

    return problem


def check_submission(contest_id: str, problem_id: str) -> Problem:
    problem = get_contest_problem(contest_id, problem_id)
    contest = get_contest_by_id(contest_id)

    contest_category = get_contest_category(contest)
    if contest_category == "Ended" and not contest.allow_upsolving:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed for this contest after it has ended."
        )

    return problem

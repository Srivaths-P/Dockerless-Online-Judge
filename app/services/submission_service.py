import json
import uuid
from typing import Optional, List

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.crud import crud_submission
from app.db import models as db_models
from app.sandbox.executor import run_code_in_sandbox
from app.schemas.submission import (
    SubmissionCreate, SubmissionStatus, SubmissionInfo, TestCaseResult,
    Submission as SubmissionSchema
)
from app.services.contest_service import get_problem_by_id


async def process_submission_async(submission_id: str, db_url: str):
    from app.db.session import SessionLocal

    db_async: Session = SessionLocal()
    try:
        submission_db = crud_submission.submission.get(db_async, id_=submission_id)
        if not submission_db:
            print(f"Error: Submission {submission_id} not found for async processing.")
            return

        submission_db.status = SubmissionStatus.RUNNING.value
        db_async.commit()

        problem = get_problem_by_id(submission_db.contest_id, submission_db.problem_id)
        if not problem:
            submission_db.status = SubmissionStatus.INTERNAL_ERROR.value
            error_result = TestCaseResult(test_case_name="Setup", status=SubmissionStatus.INTERNAL_ERROR,
                                          stderr="Problem definition not found")
            submission_db.results_json = json.dumps([error_result.model_dump()])
            db_async.commit()
            print(f"Submission {submission_id}: Problem definition not found.")
            return

        final_results_pydantic: List[TestCaseResult] = []
        overall_status = SubmissionStatus.ACCEPTED

        for tc_index, tc_schema in enumerate(problem.test_cases):
            try:
                tc_result_pydantic = await run_code_in_sandbox(
                    submission_id=uuid.UUID(submission_db.id),
                    code=submission_db.code,
                    problem=problem,
                    test_case=tc_schema,
                    language=submission_db.language
                )
                final_results_pydantic.append(tc_result_pydantic)

                if tc_result_pydantic.status != SubmissionStatus.ACCEPTED:
                    overall_status = tc_result_pydantic.status
                    if tc_result_pydantic.status == SubmissionStatus.COMPILATION_ERROR:
                        break
                    break
            except Exception as e:
                error_tc_result = TestCaseResult(
                    test_case_name=tc_schema.name, status=SubmissionStatus.INTERNAL_ERROR,
                    stderr=f"Error during test case execution setup: {str(e)}"
                )
                final_results_pydantic.append(error_tc_result)
                overall_status = SubmissionStatus.INTERNAL_ERROR
                break

        crud_submission.submission.update_submission_results(
            db_async,
            db_obj=submission_db,
            status=overall_status.value,
            results=final_results_pydantic
        )
    except Exception as e_outer:
        print(f"Outer error in process_submission_async for {submission_id}: {e_outer}")
        submission_db_final_error = crud_submission.submission.get(db_async, id_=submission_id)
        if submission_db_final_error:
            submission_db_final_error.status = SubmissionStatus.INTERNAL_ERROR.value
            error_result = TestCaseResult(test_case_name="Processing", status=SubmissionStatus.INTERNAL_ERROR,
                                          stderr=f"Overall processing error: {str(e_outer)}")
            submission_db_final_error.results_json = json.dumps([error_result.model_dump()])
            db_async.commit()
    finally:
        db_async.close()


async def create_submission(
        db: Session,
        submission_data: SubmissionCreate,
        current_user: db_models.User,
        background_tasks: BackgroundTasks
) -> SubmissionInfo:
    problem = get_problem_by_id(submission_data.contest_id, submission_data.problem_id)
    if not problem:
        raise ValueError("Problem not found")
    if submission_data.language not in problem.allowed_languages:
        raise ValueError(f"Language {submission_data.language} not allowed for this problem.")

    db_submission = crud_submission.submission.create_with_owner(
        db, obj_in=submission_data, submitter_id=current_user.id
    )

    background_tasks.add_task(process_submission_async, db_submission.id, app_settings.DATABASE_URL)

    return SubmissionInfo(
        id=db_submission.id,
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        user_email=current_user.email,
        language=db_submission.language,
        status=SubmissionStatus(db_submission.status),
        submitted_at=db_submission.submitted_at
    )


def get_submission_by_id(db: Session, submission_id: str, current_user: db_models.User) -> Optional[SubmissionSchema]:
    db_submission = crud_submission.submission.get_submission_with_owner_info(
        db, id=submission_id, submitter_id=current_user.id
    )
    if not db_submission:
        return None

    parsed_results: List[TestCaseResult] = []
    if db_submission.results_json:
        try:
            results_list_of_dicts = json.loads(db_submission.results_json)

            if isinstance(results_list_of_dicts, list):
                parsed_results = [TestCaseResult(**res_dict) for res_dict in results_list_of_dicts if
                                  isinstance(res_dict, dict)]
            else:
                print(f"Warning: results_json for submission {db_submission.id} is not a list.")

        except json.JSONDecodeError:
            print(f"Error decoding results_json for submission {db_submission.id}")
            parsed_results = [TestCaseResult(test_case_name="Results", status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr="Failed to parse results")]
        except Exception as e:
            print(f"Error creating TestCaseResult models for submission {db_submission.id}: {e}")
            parsed_results = [TestCaseResult(test_case_name="Results", status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr=f"Failed to process results: {e}")]

    return SubmissionSchema(
        id=db_submission.id,
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        language=db_submission.language,
        code=db_submission.code,
        submitter_id=db_submission.submitter_id,
        status=SubmissionStatus(db_submission.status),
        results=parsed_results,
        submitted_at=db_submission.submitted_at
    )


def get_all_submissions_for_user(db: Session, current_user: db_models.User) -> List[SubmissionInfo]:
    db_submissions = crud_submission.submission.get_multi_by_owner(db, submitter_id=current_user.id)

    submissions_info_list: List[SubmissionInfo] = []
    for sub in db_submissions:

        submission_language_str = sub.language if sub.language is not None else "N/A"

        try:
            submission_status_enum = SubmissionStatus(sub.status)
        except ValueError:
            print(
                f"Warning: DB status '{sub.status}' is not a valid SubmissionStatus enum value for submission {sub.id[:8]}...")
            submission_status_enum = SubmissionStatus.INTERNAL_ERROR

        submissions_info_list.append(
            SubmissionInfo(
                id=sub.id,
                problem_id=sub.problem_id,
                contest_id=sub.contest_id,
                user_email=current_user.email,
                language=submission_language_str,
                status=submission_status_enum,
                submitted_at=sub.submitted_at
            )
        )
    return sorted(submissions_info_list, key=lambda sub: sub.submitted_at, reverse=True)

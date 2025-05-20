import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging_config import log_user_event
from app.crud import crud_submission
from app.db import models as db_models
from app.sandbox.executor import submission_processing_queue
from app.schemas.submission import (
    SubmissionCreate, SubmissionStatus, SubmissionInfo, TestCaseResult,
    Submission as SubmissionSchema
)
from app.services.contest_service import get_problem_by_id

DEFAULT_SUBMISSION_COOLDOWN_SEC = 10


async def create_submission(
        db: Session,
        submission_data: SubmissionCreate,
        current_user: db_models.User
) -> SubmissionInfo:
    print(f"Service: create_submission called by user {current_user.email} for problem {submission_data.problem_id}")

    problem = get_problem_by_id(submission_data.contest_id, submission_data.problem_id)
    if not problem:
        print(f"Service: Problem not found: {submission_data.contest_id}/{submission_data.problem_id}")
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_create_failed",
                       details={"contest_id": submission_data.contest_id, "problem_id": submission_data.problem_id,
                                "language": submission_data.language, "detail": "Problem not found",
                                "status_code": status.HTTP_404_NOT_FOUND})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")

    if submission_data.language not in problem.allowed_languages:
        print(f"Service: Language '{submission_data.language}' not allowed for problem {problem.id}")
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_create_failed",
                       details={"contest_id": submission_data.contest_id, "problem_id": submission_data.problem_id,
                                "language": submission_data.language,
                                "detail": f"Language {submission_data.language} not allowed",
                                "status_code": status.HTTP_400_BAD_REQUEST})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Language {submission_data.language} not allowed for this problem.")

    now = datetime.now(timezone.utc)
    cooldown_sec = problem.submission_cooldown_sec if problem.submission_cooldown_sec is not None else DEFAULT_SUBMISSION_COOLDOWN_SEC
    cooldown_period = timedelta(seconds=cooldown_sec)

    last_sub_at_aware = current_user.last_submission_at
    if last_sub_at_aware and last_sub_at_aware.tzinfo is None:
        last_sub_at_aware = last_sub_at_aware.replace(tzinfo=timezone.utc)

    if last_sub_at_aware and (now - last_sub_at_aware) < cooldown_period:
        remaining_wait = (last_sub_at_aware + cooldown_period - now).total_seconds()
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_rate_limited",
                       details={"contest_id": submission_data.contest_id, "problem_id": submission_data.problem_id,
                                "language": submission_data.language, "wait_seconds": remaining_wait})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining_wait:.1f} seconds before submitting again."
        )

    db_submission = None
    try:
        print(f"Service: Calling crud_submission.submission.create_with_owner...")
        db_submission = crud_submission.submission.create_with_owner(
            db=db, obj_in=submission_data, submitter_id=current_user.id
        )
        submission_id_str = str(db_submission.id)

        current_user.last_submission_at = now
        db.merge(current_user)
        db.commit()
        db.refresh(db_submission)


    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_create_error",
                       details={"contest_id": submission_data.contest_id, "problem_id": submission_data.problem_id,
                                "language": submission_data.language, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to save submission record.") from e

    asyncio.create_task(submission_processing_queue.enqueue(submission_id_str))
    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_created_enqueued",
                   details={"contest_id": submission_data.contest_id, "problem_id": submission_data.problem_id,
                            "language": submission_data.language, "submission_id": submission_id_str})
    print(f"Service: Submission {submission_id_str[:8]} enqueued for processing.")

    submitter = db_submission.submitter
    user_email = submitter.email if submitter else current_user.email

    return SubmissionInfo(
        id=submission_id_str,
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        user_email=user_email,
        language=db_submission.language,
        status=SubmissionStatus(db_submission.status),
        submitted_at=db_submission.submitted_at
    )


def get_submission_by_id(
        db: Session,
        submission_id: str,
        current_user: db_models.User
) -> SubmissionSchema:
    db_submission = crud_submission.submission.get_submission_with_owner_info(
        db, id=submission_id, submitter_id=current_user.id
    )

    if not db_submission:
        print(f"Service: Submission {submission_id} not found in DB or does not belong to user {current_user.id}.")
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="submission_view_failed",
                       details={"submission_id": submission_id, "detail": "Not found or authorized",
                                "status_code": status.HTTP_404_NOT_FOUND})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found or not authorized.")

    parsed_results: List[TestCaseResult] = []
    if db_submission.results_json:
        try:
            results_list_of_dicts = json.loads(db_submission.results_json)
            if isinstance(results_list_of_dicts, list):
                parsed_results = []
                for res_dict in results_list_of_dicts:
                    if isinstance(res_dict, dict):
                        try:
                            parsed_results.append(TestCaseResult(**res_dict))
                        except Exception as parse_e:
                            print(
                                f"Warning: Failed to parse TestCaseResult item for submission {db_submission.id}: {parse_e}")
                            parsed_results.append(TestCaseResult(
                                test_case_name="Result Parsing Error",
                                status=SubmissionStatus.INTERNAL_ERROR,
                                stderr=f"Failed to parse result item: {parse_e}"
                            ))
                    else:
                        print(
                            f"Warning: Unexpected item type in results_json list for submission {db_submission.id}: {type(res_dict)}")
                        parsed_results.append(TestCaseResult(
                            test_case_name="Result Parsing Error",
                            status=SubmissionStatus.INTERNAL_ERROR,
                            stderr="Unexpected item type in results list."
                        ))
            else:
                print(
                    f"Warning: Service: results_json for submission {db_submission.id} is not a list: {type(results_list_of_dicts)}")
                parsed_results = [TestCaseResult(test_case_name="Result Parsing",
                                                 status=SubmissionStatus.INTERNAL_ERROR,
                                                 stderr="Invalid result format stored (not a list).")]
        except json.JSONDecodeError:
            print(f"Error decoding results_json for submission {db_submission.id}")
            parsed_results = [TestCaseResult(test_case_name="Result Parsing",
                                             status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr="Failed to parse results JSON.")]
        except Exception as e:
            print(f"Error processing results_json for submission {db_submission.id}: {e}")
            parsed_results = [TestCaseResult(test_case_name="Result Processing",
                                             status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr=f"Failed to process results: {e}")]

    try:
        status_enum = SubmissionStatus(db_submission.status)
    except ValueError:
        print(
            f"Warning: Service: Invalid status value '{db_submission.status}' in DB for submission {db_submission.id}. Defaulting to INTERNAL_ERROR.")
        status_enum = SubmissionStatus.INTERNAL_ERROR

    submitter = db_submission.submitter
    user_email = submitter.email if submitter else "Unknown User"

    return SubmissionSchema(
        id=str(db_submission.id),
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        language=db_submission.language,
        code=db_submission.code,
        submitter_id=db_submission.submitter_id,
        status=status_enum,
        results=parsed_results,
        submitted_at=db_submission.submitted_at,
        user_email=user_email
    )


def get_all_submissions_for_user(
        db: Session,
        current_user: db_models.User
) -> List[SubmissionInfo]:
    db_submissions = crud_submission.submission.get_multi_by_owner(
        db, submitter_id=current_user.id, skip=0, limit=100
    )

    submissions_info_list: List[SubmissionInfo] = []
    for sub in db_submissions:
        try:
            status_enum = SubmissionStatus(sub.status)
        except ValueError:
            status_enum = SubmissionStatus.INTERNAL_ERROR

        submissions_info_list.append(
            SubmissionInfo(
                id=str(sub.id),
                problem_id=sub.problem_id,
                contest_id=sub.contest_id,
                user_email=current_user.email,
                language=sub.language,
                status=status_enum,
                submitted_at=sub.submitted_at
            )
        )
    return sorted(submissions_info_list, key=lambda s: s.submitted_at, reverse=True)

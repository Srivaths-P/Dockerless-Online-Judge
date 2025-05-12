
import asyncio
import json
from typing import List

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from app.crud import crud_submission
from app.db import models as db_models
from app.db.session import get_db
from app.sandbox.executor import submission_processing_queue
from app.schemas.submission import (
    SubmissionCreate, SubmissionStatus, SubmissionInfo, TestCaseResult,
    Submission as SubmissionSchema
)
from app.services.contest_service import get_problem_by_id


async def get_current_active_user(db: Session = Depends(get_db)) -> db_models.User:
    user = db.query(db_models.User).filter(db_models.User.email == "asd@asd.com").first()
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def create_submission(
        db: Session,
        submission_data: SubmissionCreate,
        current_user: db_models.User = Depends(get_current_active_user)
) -> SubmissionInfo:
    print(f"Service: create_submission called by user {current_user.email} for problem {submission_data.problem_id}")

    problem = get_problem_by_id(submission_data.contest_id, submission_data.problem_id)
    if not problem:
        print(f"Service: Problem not found: {submission_data.contest_id}/{submission_data.problem_id}")
        raise HTTPException(status_code=404, detail="Problem not found")
    if submission_data.language not in problem.allowed_languages:
        print(f"Service: Language '{submission_data.language}' not allowed for problem {problem.id}")
        raise HTTPException(status_code=400,
                            detail=f"Language {submission_data.language} not allowed for this problem.")

    try:
        print(f"Service: Calling crud_submission.submission.create_with_owner...")
        db_submission = crud_submission.submission.create_with_owner(
            db=db, obj_in=submission_data, submitter_id=current_user.id
        )
        submission_id_str = str(db_submission.id)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to save submission record.") from e

    asyncio.create_task(submission_processing_queue.enqueue(submission_id_str))
    print(f"Service: Submission {submission_id_str[:8]} enqueued for processing.")

    return SubmissionInfo(
        id=submission_id_str,
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        user_email=current_user.email,
        language=db_submission.language,
        status=SubmissionStatus(db_submission.status),
        submitted_at=db_submission.submitted_at
    )


def get_submission_by_id(
        db: Session,
        submission_id: str,
        current_user: db_models.User = Depends(get_current_active_user)
) -> SubmissionSchema:
    db_submission = crud_submission.submission.get(db, id_=submission_id)

    if not db_submission:
        print(f"Service: Submission {submission_id} not found in DB.")
        raise HTTPException(status_code=404, detail="Submission not found.")

    if db_submission.submitter_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this submission.")

    parsed_results: List[TestCaseResult] = []
    if db_submission.results_json:
        try:
            results_list_of_dicts = json.loads(db_submission.results_json)
            if isinstance(results_list_of_dicts, list):
                parsed_results = [TestCaseResult(**res_dict)
                                  for res_dict in results_list_of_dicts if isinstance(res_dict, dict)]
            else:
                print(
                    f"Warning: Service: results_json for submission {db_submission.id} is not a list: {type(results_list_of_dicts)}")
                parsed_results = [TestCaseResult(test_case_name="Result Parsing",
                                                 status=SubmissionStatus.INTERNAL_ERROR,
                                                 stderr="Invalid result format stored.")]
        except json.JSONDecodeError:
            print(f"Error decoding results_json for submission {db_submission.id}")
            parsed_results = [TestCaseResult(test_case_name="Result Parsing",
                                             status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr="Failed to parse results JSON.")]
        except Exception as e:
            print(f"Error creating TestCaseResult models for submission {db_submission.id}: {e}")
            parsed_results = [TestCaseResult(test_case_name="Result Processing",
                                             status=SubmissionStatus.INTERNAL_ERROR,
                                             stderr=f"Failed to process results: {e}")]

    try:
        status_enum = SubmissionStatus(db_submission.status)
    except ValueError:
        print(
            f"Warning: Service: Invalid status value '{db_submission.status}' in DB for submission {db_submission.id}. Defaulting to INTERNAL_ERROR.")
        status_enum = SubmissionStatus.INTERNAL_ERROR

    return SubmissionSchema(
        id=str(db_submission.id),
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        language=db_submission.language,
        code=db_submission.code,
        submitter_id=db_submission.submitter_id,
        status=status_enum,
        results=parsed_results,
        submitted_at=db_submission.submitted_at
    )


def get_all_submissions_for_user(
        db: Session = Depends(get_db),
        current_user: db_models.User = Depends(get_current_active_user)
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

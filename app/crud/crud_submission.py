import json
import logging
import traceback
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Submission
from app.schemas.submission import SubmissionCreate, SubmissionUpdate, TestCaseResult, SubmissionStatus

logger = logging.getLogger(__name__)


class CRUDSubmission(CRUDBase[Submission, SubmissionCreate, SubmissionUpdate]):
    def get(self, db: Session, id_: Any) -> Optional[Submission]:
        if isinstance(id_, uuid.UUID):
            id_str = str(id_)
        elif isinstance(id_, str):
            id_str = id_
            try:
                uuid.UUID(id_str)
            except ValueError:
                logger.warning(f"CRUD: Invalid UUID string format provided to get: {id_str}")
                return None
        else:
            logger.warning(f"CRUD: Unexpected ID type for get: {type(id_)}")
            return None

        return db.query(self.model).filter(self.model.id == id_str).first()

    @staticmethod
    def create_with_owner(
            db: Session, *, obj_in: SubmissionCreate, submitter_id: int
    ) -> Submission:
        results_list_for_json: List[Dict] = []
        db_obj = Submission(
            problem_id=obj_in.problem_id,
            contest_id=obj_in.contest_id,
            language=obj_in.language,
            code=obj_in.code,
            submitter_id=submitter_id,
            status=SubmissionStatus.PENDING.value,
            results_json=json.dumps(results_list_for_json)
        )
        db.add(db_obj)

        try:
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except Exception as e:
            logger.error(f"Failed to create submission for owner {submitter_id}", exc_info=True)
            db.rollback()
            raise

    def get_multi_by_owner(
            self, db: Session, *, submitter_id: int, skip: int = 0, limit: int = 100
    ) -> List[Submission]:
        return (
            db.query(self.model)
            .filter(Submission.submitter_id == submitter_id)
            .order_by(desc(Submission.submitted_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_user_contest_submissions(
            self, db: Session, *, submitter_id: int, contest_id: str
    ) -> List[Submission]:
        return (
            db.query(self.model)
            .filter(
                Submission.submitter_id == submitter_id,
                Submission.contest_id == contest_id
            )
            .order_by(self.model.submitted_at.asc())
            .all()
        )

    @staticmethod
    def update_submission_results(
            db: Session,
            *,
            db_obj: Submission,
            status: str,
            results: List[TestCaseResult]
    ) -> Submission:
        try:
            db.merge(db_obj)
        except Exception as e:
            db.rollback()
            raise

        results_list_of_dicts = [result.model_dump() for result in results]
        db_obj.results_json = json.dumps(results_list_of_dicts)
        db_obj.status = status

        try:
            db.commit()
            return db_obj
        except Exception as e:
            logger.error(f"Failed to update submission results for {db_obj.id}", exc_info=True)
            db.rollback()
            raise

    def get_user_submission(self, db: Session, id: str, submitter_id: int) -> Optional[Submission]:
        try:
            uuid.UUID(id)
        except ValueError:
            return None

        return (
            db.query(self.model)
            .filter(self.model.id == id, self.model.submitter_id == submitter_id)
            .first()
        )


submission = CRUDSubmission(Submission)

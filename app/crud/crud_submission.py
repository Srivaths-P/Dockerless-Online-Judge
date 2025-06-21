import json
import traceback
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Submission
from app.schemas.submission import SubmissionCreate, SubmissionUpdate, TestCaseResult


class CRUDSubmission(CRUDBase[Submission, SubmissionCreate, SubmissionUpdate]):
    def get(self, db: Session, id_: Any) -> Optional[Submission]:
        if isinstance(id_, uuid.UUID):
            id_str = str(id_)
        elif isinstance(id_, str):
            id_str = id_
            try:
                uuid.UUID(id_str)
            except ValueError:
                print(f"CRUD: Invalid UUID string format provided to get: {id_str}")
                return None
        else:
            print(f"CRUD: Unexpected ID type for get: {type(id_)}")
            return None

        return db.query(self.model).filter(self.model.id == id_str).first()

    def create_with_owner(
            self, db: Session, *, obj_in: SubmissionCreate, submitter_id: int
    ) -> Submission:
        results_list_for_json: List[Dict] = []
        db_obj = Submission(
            problem_id=obj_in.problem_id,
            contest_id=obj_in.contest_id,
            language=obj_in.language,
            code=obj_in.code,
            submitter_id=submitter_id,
            status="PENDING",
            results_json=json.dumps(results_list_for_json)
        )
        db.add(db_obj)

        try:
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except Exception as e:
            traceback.print_exc()
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

    def get_user_submissions_for_contest(
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

    def update_submission_results(
            self,
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
            traceback.print_exc()
            db.rollback()
            raise

    def get_submission_with_owner_info(self, db: Session, id: str, submitter_id: int) -> Optional[Submission]:
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

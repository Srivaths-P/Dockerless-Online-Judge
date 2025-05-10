import json
from typing import List, Optional, Dict

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Submission
from app.schemas.submission import SubmissionCreate, SubmissionUpdate, TestCaseResult


class CRUDSubmission(CRUDBase[Submission, SubmissionCreate, SubmissionUpdate]):
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
        db.commit()
        db.refresh(db_obj)
        return db_obj

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

    def update_submission_results(
            self,
            db: Session,
            *,
            db_obj: Submission,
            status: str,
            results: List[TestCaseResult]
    ) -> Submission:
        results_list_of_dicts = [result.model_dump() for result in results]
        db_obj.results_json = json.dumps(results_list_of_dicts)
        db_obj.status = status

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_submission_with_owner_info(self, db: Session, id: str, submitter_id: int) -> Optional[Submission]:
        """ Get a specific submission by ID, ensuring it belongs to the specified owner. """
        return (
            db.query(self.model)
            .filter(self.model.id == id, self.model.submitter_id == submitter_id)
            .first()
        )


submission = CRUDSubmission(Submission)

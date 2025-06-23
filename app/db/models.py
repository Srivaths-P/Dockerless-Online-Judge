import uuid as uuid_pkg
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean(), default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    last_submission_at = Column(DateTime(timezone=True), nullable=True)
    last_generation_at = Column(DateTime(timezone=True), nullable=True)

    submissions = relationship("Submission", back_populates="submitter")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid_pkg.uuid4()))
    problem_id = Column(String, nullable=False, index=True)
    contest_id = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False)
    code = Column(Text, nullable=False)

    submitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitter = relationship("User", back_populates="submissions")

    status = Column(String, default="PENDING", nullable=False)
    results_json = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

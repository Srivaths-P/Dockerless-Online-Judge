import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from pytest_mock import MockerFixture

from app.db.models import User
from app.schemas.problem import Problem

pytestmark = pytest.mark.asyncio


MOCK_PROBLEM_ID = "mock-problem-1"
MOCK_CONTEST_ID = "mock-contest-1"


@pytest.fixture
def mock_problem() -> Problem:
    return Problem(
        id=MOCK_PROBLEM_ID,
        title="Mock Problem",
        description_md="A test problem",
        time_limit_sec=2,
        memory_limit_mb=128,
        allowed_languages=["python", "c++"],
        submission_cooldown_sec=5,
    )


def apply_mocks(mocker: MockerFixture, mock_problem: Problem):
    mocker.patch(
        "app.api.v1.endpoints.submissions.contest_service.get_contest_problem",
        return_value=mock_problem,
    )

    mocker.patch(
        "app.services.submission_service.check_submission",
        return_value=mock_problem,
    )


async def test_create_submission_success(
    authenticated_client: AsyncClient,
    test_user: User,
    db: Session,
    mocker: MockerFixture,
    mock_problem: Problem,
):
    apply_mocks(mocker, mock_problem)
    mock_enqueue = mocker.patch("app.sandbox.executor.submission_processing_queue.enqueue")

    submission_data = {
        "contest_id": MOCK_CONTEST_ID,
        "problem_id": MOCK_PROBLEM_ID,
        "language": "python",
        "code": "print('hello')"
    }

    response = await authenticated_client.post("/api/v1/submissions/", json=submission_data)

    assert response.status_code == 202, f"Response: {response.text}"
    response_data = response.json()
    assert response_data["problem_id"] == MOCK_PROBLEM_ID
    assert response_data["status"] == "PENDING"
    assert response_data["user_email"] == test_user.email

    mock_enqueue.assert_called_once()


async def test_create_submission_rate_limited(
    authenticated_client: AsyncClient,
    db: Session,
    mocker: MockerFixture,
    mock_problem: Problem,
):
    apply_mocks(mocker, mock_problem)

    submission_data = {
        "contest_id": MOCK_CONTEST_ID,
        "problem_id": MOCK_PROBLEM_ID,
        "language": "python",
        "code": "print('hello')"
    }

    response1 = await authenticated_client.post("/api/v1/submissions/", json=submission_data)
    assert response1.status_code == 202, f"The first submission failed: {response1.text}"

    response2 = await authenticated_client.post("/api/v1/submissions/", json=submission_data)
    assert response2.status_code == 429
    assert "Please wait" in response2.json()["detail"]

from fastapi.testclient import TestClient

CONTEST_ID = "test-contest-1"
PROBLEM_ID = "add-two"
CORRECT_PYTHON_CODE = "a, b = map(int, input().split())\nprint(a + b)"
WRONG_LANGUAGE = "javascript"


def test_create_submission(client: TestClient, auth_token_headers: dict[str, str]):
    response = client.post(
        "/api/v1/submissions/",
        headers=auth_token_headers,
        json={
            "contest_id": CONTEST_ID,
            "problem_id": PROBLEM_ID,
            "language": "python",
            "code": CORRECT_PYTHON_CODE,
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["problem_id"] == PROBLEM_ID
    assert data["status"] == "PENDING"


def test_create_submission_rate_limited(client: TestClient, auth_token_headers: dict[str, str]):
    client.post(
        "/api/v1/submissions/",
        headers=auth_token_headers,
        json={
            "contest_id": CONTEST_ID,
            "problem_id": PROBLEM_ID,
            "language": "python",
            "code": CORRECT_PYTHON_CODE,
        },
    )
    response = client.post(
        "/api/v1/submissions/",
        headers=auth_token_headers,
        json={
            "contest_id": CONTEST_ID,
            "problem_id": PROBLEM_ID,
            "language": "python",
            "code": CORRECT_PYTHON_CODE,
        },
    )
    assert response.status_code == 429


def test_create_submission_wrong_language(client: TestClient, auth_token_headers: dict[str, str]):
    response = client.post(
        "/api/v1/submissions/",
        headers=auth_token_headers,
        json={
            "contest_id": CONTEST_ID,
            "problem_id": PROBLEM_ID,
            "language": WRONG_LANGUAGE,
            "code": "console.log('wrong lang');",
        },
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import User


def test_get_current_user(client: TestClient, test_user: User):
    access_token = create_access_token(data={"sub": test_user.email})
    client.cookies.set("access_token_cookie", access_token)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
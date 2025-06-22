from fastapi.testclient import TestClient


def test_register_user(client: TestClient):
    response = client.post("/api/v1/auth/register", json={"email": "register@example.com", "password": "password"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "register@example.com"
    assert "id" in data
    assert "hashed_password" not in data


def test_register_existing_user(client: TestClient):
    client.post("/api/v1/auth/register", json={"email": "existing@example.com", "password": "password"})
    response = client.post("/api/v1/auth/register", json={"email": "existing@example.com", "password": "password"})
    assert response.status_code == 400


def test_login_for_access_token(client: TestClient):
    client.post("/api/v1/auth/register", json={"email": "login@example.com", "password": "password"})
    response = client.post("/api/v1/auth/token", data={"username": "login@example.com", "password": "password"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_get_current_user(client: TestClient, auth_token_headers: dict[str, str]):
    response = client.get("/api/v1/auth/me", headers=auth_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"

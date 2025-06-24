from fastapi import status
from fastapi.testclient import TestClient

from app.db.models import User


def test_home_page_unauthenticated(client: TestClient):
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "Sign in with Google" in response.text


def test_contests_page_redirects_unauthenticated(client: TestClient):
    response = client.get("/contests/", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/auth/login" in response.headers["location"]


def test_login_redirects_to_google(client: TestClient):
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND
    assert "accounts.google.com" in response.headers["location"]


def test_home_page_view_when_authenticated(client: TestClient, test_user: User):
    from app.core.security import create_access_token
    access_token = create_access_token(data={"sub": test_user.email})
    client.cookies.set("access_token_cookie", access_token)

    home_response = client.get("/")
    assert home_response.status_code == status.HTTP_200_OK
    assert "You are logged in as <strong>test@example.com</strong>" in home_response.text

    contests_response = client.get("/contests/")
    assert contests_response.status_code == status.HTTP_200_OK

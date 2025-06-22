from fastapi import status
from fastapi.testclient import TestClient

from app.db.models import User


def test_home_page_unauthenticated(client: TestClient):
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "Login" in response.text
    assert "Register" in response.text


def test_contests_page_redirects_unauthenticated(client: TestClient):
    response = client.get("/contests/", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith("/auth/login")


def test_login_page(client: TestClient):
    response = client.get("/auth/login")
    assert response.status_code == status.HTTP_200_OK
    assert "Login" in response.text


def test_successful_login_and_home_page_view(client: TestClient, test_user: User):
    response = client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "password"},
        follow_redirects=False
    )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith("/")
    assert "access_token_cookie" in response.cookies

    home_response = client.get("/")
    assert home_response.status_code == status.HTTP_200_OK
    assert "You are logged in as <strong>test@example.com</strong>" in home_response.text

    contests_response = client.get("/contests/")
    assert contests_response.status_code == status.HTTP_200_OK
    assert "Test Contest 1" in contests_response.text

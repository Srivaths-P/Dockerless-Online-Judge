from sqlalchemy.orm import Session

from app.crud import crud_user
from app.schemas.user import UserCreate


def test_create_user(db_session: Session):
    email = "newuser@example.com"
    password = "newpassword"
    user_in = UserCreate(email=email, password=password)
    user = crud_user.user.create(db_session, obj_in=user_in)
    assert user.email == email
    assert hasattr(user, "hashed_password")


def test_authenticate_user(db_session: Session):
    email = "authuser@example.com"
    password = "authpassword"
    user_in = UserCreate(email=email, password=password)
    crud_user.user.create(db_session, obj_in=user_in)

    authenticated_user = crud_user.user.authenticate(db_session, email=email, password=password)
    assert authenticated_user
    assert authenticated_user.email == email

    wrong_password_user = crud_user.user.authenticate(db_session, email=email, password="wrongpassword")
    assert wrong_password_user is None

    non_existent_user = crud_user.user.authenticate(db_session, email="nonexistent@example.com", password="password")
    assert non_existent_user is None


def test_get_user_by_email(db_session: Session):
    email = "getuser@example.com"
    password = "getpassword"
    user_in = UserCreate(email=email, password=password)
    crud_user.user.create(db_session, obj_in=user_in)

    user = crud_user.user.get_by_email(db_session, email=email)
    assert user
    assert user.email == email

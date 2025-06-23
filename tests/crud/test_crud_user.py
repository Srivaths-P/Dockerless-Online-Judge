from sqlalchemy.orm import Session

from app.crud import crud_user
from app.schemas.user import UserCreate


def test_create_user(db_session: Session):
    email = "newuser@example.com"
    user_in = UserCreate(email=email)
    user = crud_user.user.create(db_session, obj_in=user_in)
    assert user.email == email
    assert not hasattr(user, "hashed_password")


def test_get_user_by_email(db_session: Session):
    email = "getuser@example.com"
    user_in = UserCreate(email=email)
    crud_user.user.create(db_session, obj_in=user_in)

    user = crud_user.user.get_by_email(db_session, email=email)
    assert user
    assert user.email == email

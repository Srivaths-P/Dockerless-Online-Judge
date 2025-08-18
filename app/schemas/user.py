from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserPublicBase(UserBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserPublic(UserPublicBase):
    pass


class UserInDB(UserPublicBase):
    pass

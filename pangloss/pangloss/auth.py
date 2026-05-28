from datetime import timedelta

import bcrypt
from authx import AuthX, AuthXConfig
from pydantic import BaseModel

from pangloss.users.models import User

config = AuthXConfig()
config.JWT_HEADER_NAME = "Authorization"
config.JWT_ALGORITHM = "HS256"
config.JWT_SECRET_KEY = "SECRET_KEY"
config.JWT_TOKEN_LOCATION = ["headers", "query", "cookies", "json"]
config.JWT_CSRF_METHODS = []
config.JWT_COOKIE_SAMESITE = "none"
config.JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=1)
config.JWT_SESSION_COOKIE = True


LOGGED_IN_USER_NAME_COOKIE_NAME = "logged_in_user_name"


security = AuthX[User](config=config)


class LoginCredentials(BaseModel):
    username: str
    password: str


def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(
        bytes(plain_password, "utf-8"), bytes(hashed_password, "utf-8")
    )


def get_password_hash(plain_password: str):
    return bcrypt.hashpw(bytes(plain_password, "utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

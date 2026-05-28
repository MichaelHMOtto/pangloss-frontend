import typer
from pydantic import EmailStr, validate_email
from pydantic_core import PydanticCustomError

from pangloss.auth import get_password_hash, verify_password
from pangloss.exceptions import PanglossUserError
from pangloss.users.models import UserInDB


def get_email():
    try:
        email = validate_email(typer.prompt("Email", type=str))
        return email
    except PydanticCustomError:
        print("[red bold]Invalid email[/red bold]")
        return get_email()


async def create_user(username: str, email: EmailStr, password: str, admin: bool):
    user_to_create = UserInDB(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        admin=admin,
    )

    assert verify_password(password, user_to_create.hashed_password)

    try:
        result = await user_to_create.write_user()
        return result
    except PanglossUserError as e:
        raise e

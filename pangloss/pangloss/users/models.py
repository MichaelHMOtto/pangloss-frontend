from neo4j.exceptions import ConstraintError
from pydantic import BaseModel, EmailStr, Field

from pangloss.exceptions import PanglossUserError
from pangloss.neo4j.database import Transaction, database


class User(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None
    admin: bool = Field(default=False, json_schema_extra={"readOnly": True})
    disabled: bool = Field(default=False, json_schema_extra={"readOnly": True})


class UserView(BaseModel):
    username: str
    email: str
    full_name: str | None


class UserCreate(User):
    password: str


class UserInDB(User):
    hashed_password: str

    @database.write_transaction
    async def write_user(self, tx: Transaction):
        query = """
        CREATE (user:PGUser:PGInternal:PGCore)
        SET user = $user
        RETURN user.username
        """
        params = {"user": dict(self)}
        try:
            result = await tx.run(query, params)
            user = await result.value()
            return user[0]
        except ConstraintError:
            raise PanglossUserError("Username already exists")

    @classmethod
    @database.read_transaction
    async def get(cls, tx: Transaction, username: str) -> "UserInDB | None":
        query = """
        MATCH (user:PGUser)
        WHERE user.username = $username
        RETURN user
        """
        params = {"username": username}
        result = await tx.run(query, params)
        user = await result.value()
        try:
            if user and user[0]:
                return __class__(**user[0])
        except IndexError:
            return None

    @classmethod
    @database.read_transaction
    async def get_by_email(cls, tx: Transaction, email: str) -> "UserInDB | None":
        query = """
        MATCH (user:PGUser)
        WHERE user.username = $email
        RETURN user
        """
        params = {"email": email}
        result = await tx.run(query, params)
        user = await result.value()
        try:
            if user and user[0]:
                return __class__(**user[0])
        except IndexError:
            return None

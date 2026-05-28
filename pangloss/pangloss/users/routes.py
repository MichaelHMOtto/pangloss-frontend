from typing import Annotated, Awaitable, cast

from authx import RequestToken
from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request, Response
from pydantic import BaseModel

from pangloss.auth import (
    LOGGED_IN_USER_NAME_COOKIE_NAME,
    LoginCredentials,
    get_password_hash,
    security,
    verify_password,
)
from pangloss.users.models import User, UserCreate, UserInDB


class RefreshForm(BaseModel):
    refresh_token: str


@security.set_subject_getter  # type: ignore
async def get_user_from_uid(uid: str, *args) -> User:
    user_in_db = await UserInDB.get_by_email(email=uid)

    if user_in_db:
        return User(**dict(user_in_db))
    raise HTTPException(401, detail={"message": "Session/Token failed"})


async def get_current_active_user(
    awaitable_user: Annotated[Awaitable[User], Depends(security.get_current_subject)],
):
    current_user = await awaitable_user

    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    if not current_user.admin:
        raise HTTPException(status_code=403, detail="Not authorised")
    return current_user


def setup_user_routes(_app: FastAPI, settings) -> FastAPI:
    api_router = APIRouter(prefix="/api/users", tags=["Pangloss.User"])

    @api_router.post("/token")
    async def get_token(credentials: LoginCredentials):
        user = await UserInDB.get(credentials.username)
        if user and verify_password(credentials.password, user.hashed_password):
            token = security.create_access_token(uid=user.email)
            return {"access_token": token}
        raise HTTPException(401, detail={"message": "Bad credentials"})

    @api_router.post("/session")
    async def get_session(
        response: Response,
        username: Annotated[str, Form()],
        password: Annotated[str, Form()],
    ):
        user = await UserInDB.get(username)
        if user and verify_password(password, user.hashed_password):
            access_token = security.create_access_token(uid=user.username)
            refresh_token = security.create_refresh_token(uid=user.username)
            security.set_access_cookies(token=access_token, response=response)
            security.set_refresh_cookies(token=refresh_token, response=response)
            response.set_cookie(LOGGED_IN_USER_NAME_COOKIE_NAME, value=user.username)

            return {"message": "success"}
        raise HTTPException(401, detail={"message": "Bad credentials"})

    @api_router.delete("/session")
    async def delete_session(response: Response):
        response.delete_cookie(security.config.JWT_ACCESS_COOKIE_NAME)
        response.delete_cookie(security.config.JWT_REFRESH_COOKIE_NAME)
        response.delete_cookie(LOGGED_IN_USER_NAME_COOKIE_NAME)

        return {"message": "success"}

    @api_router.post("/session/refresh")
    async def refresh(
        request: Request, response: Response, refresh_data: RefreshForm | None = None
    ):
        """
        Refresh endpoint - creates a new access token using a refresh token

        Can accept the refresh token either:
        1. In the Authorization header
        2. In the request body as JSON
        """
        try:
            # First try to get the refresh token from the Authorization header
            try:
                refresh_payload = await security.refresh_token_required(request)
            except Exception as header_error:
                if not refresh_data or not refresh_data.refresh_token:
                    # If we don't have a token in either place, raise the original error
                    raise header_error

                # Manually decode and verify the refresh token
                token = refresh_data.refresh_token
                refresh_payload = security.verify_token(
                    cast(RequestToken, token),
                    verify_type=True,
                )
            # Create a new access token
            access_token = security.create_access_token(refresh_payload.sub)
            security.set_access_cookies(token=access_token, response=response)
            return {"access_token": access_token}
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))

    @api_router.get("/me", response_model=User)
    async def read_users_me(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ):
        return current_user

    @api_router.get("/me/items")
    async def read_own_items(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ):
        return [{"item_id": "Foo", "owner": current_user.username}]

    @api_router.post("/new", name="CreateUser")
    async def create_user(
        new_user: UserCreate,
        current_user: Annotated[User, Depends(get_current_admin_user)],
    ):
        user_to_create = UserInDB(
            username=new_user.username,
            email=new_user.email,
            hashed_password=get_password_hash(new_user.password),
        )
        result = await user_to_create.write_user()
        return result

    _app.include_router(api_router)

    return _app

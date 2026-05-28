import pytest
from pydantic import AnyHttpUrl

from pangloss.model_config.model_manager import ModelManager
from pangloss.settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "MyTestApp"
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl] = []

    DB_URL: str = "bolt://localhost:7688"
    DB_USER: str = "neo4j"
    DB_PASSWORD: str = "password"
    DB_DATABASE_NAME: str = "neo4j"

    INSTALLED_APPS: list[str] = ["pangloss_core"]
    AUTHJWT_SECRET_KEY: str = "SECRET"

    INTERFACE_LANGUAGES: list[str] = ["en"]

    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://pangloss_test.com")


settings = Settings()


@pytest.fixture(scope="function", autouse=True)
def reset_model_manager():
    ModelManager._reset()

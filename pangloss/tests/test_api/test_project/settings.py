from pydantic import AnyHttpUrl

from pangloss.settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "MyTestApp"
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl] = []

    DB_URL: str = "bolt://localhost:7688"
    DB_USER: str = "neo4j"
    DB_PASSWORD: str = "password"
    DB_DATABASE_NAME: str = "neo4j"

    INSTALLED_APPS: list[str] = ["pangloss", "tests.test_api.test_app"]
    AUTHJWT_SECRET_KEY: str = "SECRET"

    INTERFACE_LANGUAGES: list[str] = ["en"]

    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://pangloss_test.com")


settings = Settings()

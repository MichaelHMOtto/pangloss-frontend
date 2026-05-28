import pytest
import pytest_asyncio
from pydantic import AnyHttpUrl

from pangloss.settings import BaseSettings
from pangloss.testing.uvicorn import spawn_uvicorn


class Settings(BaseSettings):
    PROJECT_NAME: str = "MyTestApp"
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl] = []

    DB_URL: str = "bolt://localhost:7688"
    DB_USER: str = "neo4j"
    DB_PASSWORD: str = "password"
    DB_DATABASE_NAME: str = "neo4j"

    INSTALLED_APPS: list[str] = ["pangloss"]
    AUTHJWT_SECRET_KEY: str = "SECRET"

    INTERFACE_LANGUAGES: list[str] = ["en"]

    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://pangloss_test.com")


settings = Settings()


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
def database_setup(event_loop):
    from pangloss.indexes import _install_index_and_constraints_from_text
    from pangloss.neo4j.database import Database, DatabaseUtils, database

    Database.initialise_default_database(settings)

    event_loop.run_until_complete(DatabaseUtils.dangerously_clear_database())
    event_loop.run_until_complete(_install_index_and_constraints_from_text())
    event_loop.run_until_complete(DatabaseUtils.create_default_user())

    yield event_loop
    event_loop.run_until_complete(database.close())


@pytest.fixture(scope="session", autouse=True)
def server():
    """Fixture to start the server for testing."""

    from pangloss.model_config.model_manager import ModelManager

    ModelManager.initialise_models()

    uvicorn = spawn_uvicorn(
        working_directory=".", app="tests.test_api.test_project.main:app"
    )

    yield uvicorn
    uvicorn.process.terminate()

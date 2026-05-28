import asyncio
import contextlib
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from pangloss.auth import security
from pangloss.model_config.model_manager import ModelManager
from pangloss.neo4j.database import Database
from pangloss.settings import BaseSettings
from pangloss.users.routes import setup_user_routes

logger = logging.getLogger("uvicorn.info")
RunningBackgroundTasks = []


def get_application(settings: BaseSettings, initialise_database: bool = True):
    DEVELOPMENT_MODE = "--reload" in sys.argv  # Dumb hack!

    from pangloss.api import PanglossAPIRouter, setup_api_routes
    from pangloss.background_tasks import (
        BackgroundTaskCloseRegistry,
        BackgroundTaskRegistry,
    )
    from pangloss.initialisation import InitalisationTaskRegistery

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the ML model
        for task in BackgroundTaskRegistry:
            if not DEVELOPMENT_MODE or task["run_in_dev"]:
                running_task = asyncio.create_task(task["function"]())  # type: ignore

                RunningBackgroundTasks.append(running_task)
            else:
                logger.warning(
                    f"Skipping background task '{task['name']}' for development mode"
                )
        yield

        for task in BackgroundTaskCloseRegistry:
            await task()

        logging.info("Closing background tasks...")
        for task in RunningBackgroundTasks:
            task.cancel()

        logging.info("Background tasks closed")

    for installed_app in settings.INSTALLED_APPS:
        __import__(installed_app)
        __import__(f"{installed_app}.models", locals=locals())

        try:
            __import__(f"{installed_app}.background_tasks")
        except Exception as e:
            e.add_note(f"Failed to import background_tasks for {installed_app}")

        try:
            __import__(f"{installed_app}.initialisation")
        except Exception:
            pass

    ModelManager.initialise_models()
    if initialise_database:
        Database.initialise_default_database(settings)
    _app: FastAPI = FastAPI(
        title=settings.PROJECT_NAME,
        swagger_ui_parameters={"defaultModelExpandDepth": 1, "deepLinking": True},
        lifespan=lifespan,
    )

    _app = setup_api_routes(_app, settings)
    _app = setup_user_routes(_app, settings)

    for installed_app in settings.INSTALLED_APPS:
        try:
            __import__(f"{installed_app}.api")
        except Exception:
            pass

    for pangloss_api_routers in PanglossAPIRouter.instances:
        _app.include_router(pangloss_api_routers.instance)
        
    cors_origins = [str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS]
    if DEVELOPMENT_MODE and "http://localhost:3000" not in cors_origins:
        cors_origins.append("http://localhost:3000")

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _app.add_middleware(GZipMiddleware, minimum_size=400)
    security.handle_errors(_app)
    for task in InitalisationTaskRegistery:
        if task.get("run_in_dev", False) and DEVELOPMENT_MODE:
            logger.info(f"Initialising: {task['name']}")
            task["function"]()
        if task.get("dev_only", False) and not DEVELOPMENT_MODE:
            pass

        if not task.get("dev_only", False) and not DEVELOPMENT_MODE:
            logger.info(f"Initialising: {task['name']}")
            task["function"]()

    return _app

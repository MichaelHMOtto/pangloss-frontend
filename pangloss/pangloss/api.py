import asyncio
import typing
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from humps import pascalize
from pydantic import AnyHttpUrl, BaseModel
from ulid import ULID

from pangloss.exceptions import PanglossNotFoundError
from pangloss.model_config.model_manager import ModelManager
from pangloss.model_config.model_setup_functions.utils import get_all_subclasses
from pangloss.model_config.models_base import CreateBase
from pangloss.models import BaseNode
from pangloss.neo4j.utils import SearchResultObject
from pangloss.users.routes import User, get_current_active_user

if typing.TYPE_CHECKING:
    from pangloss.settings import BaseSettings


from typing import NamedTuple


class APIRouterInstance(NamedTuple):
    instance: "PanglossAPIRouter"
    module: str


class PanglossAPIRouter(APIRouter):
    """A subclass of FastAPI.APIRouter that keeps track of its instances and installs them as endpoints at startup"""

    instances: list[APIRouterInstance] = []

    def __init__(self, *args, **kwargs):
        __class__.instances.append(APIRouterInstance(self, self.__module__))
        super().__init__(*args, **kwargs)


class DeferredQueryRunner:
    """A class to manage deferred queries for creating and updating instances.
    It uses asyncio tasks to run the deferred queries in the background.

    If a deferred query is already running for a specific instance,
    it will cancel the existing deferred query.
    """

    deferred_queries_lock = Lock()

    creation_deferred_tasks: dict[str, asyncio.Task] = {}
    updating_deferred_tasks: dict[str, asyncio.Task] = {}

    @classmethod
    def run_deferred_create(cls, instance_id: ULID, task: typing.Callable) -> None:
        task_id = str(instance_id)
        with cls.deferred_queries_lock:
            cls.creation_deferred_tasks[task_id] = asyncio.create_task(task())

        def on_complete(a):
            with cls.deferred_queries_lock:
                cls.creation_deferred_tasks.pop(task_id, None)

        with cls.deferred_queries_lock:
            cls.creation_deferred_tasks[task_id].add_done_callback(on_complete)

    @classmethod
    def run_deferred_update(cls, instance_id: ULID, task: typing.Callable) -> None:
        task_id = str(instance_id)

        with cls.deferred_queries_lock:
            cls.updating_deferred_tasks[task_id] = asyncio.create_task(task())

        def on_complete(a):
            with cls.deferred_queries_lock:
                cls.updating_deferred_tasks.pop(task_id, None)

        with cls.deferred_queries_lock:
            cls.updating_deferred_tasks[task_id].add_done_callback(on_complete)

    @classmethod
    def stop_deferred(cls, instance_id: ULID) -> None:
        task_id = str(instance_id)
        with cls.deferred_queries_lock:
            if task_id in cls.creation_deferred_tasks:
                cls.creation_deferred_tasks[task_id].cancel()
            if task_id in cls.updating_deferred_tasks:
                cls.updating_deferred_tasks[task_id].cancel()


class SuccessResponse(BaseModel):
    detail: str


class ErrorResponse(BaseModel):
    detail: str


class ListResponse[T](typing.TypedDict):
    results: typing.List[T]
    page: int
    count: int
    totalPages: int
    nextPage: int | None
    previousPage: int | None
    nextUrl: AnyHttpUrl | None
    previousUrl: AnyHttpUrl | None


def build_list_handler(model: type[BaseNode]):
    # Lists should also show any subclass of the model type,
    # so we need to allow this by getting all subclasses
    model_subclasses = get_all_subclasses(model)
    model_subclasses.add(model)
    allowed_types = (
        typing.Union[*(m.ReferenceView for m in model_subclasses)]  # type: ignore
        if model_subclasses
        else model.ReferenceView
    )

    async def list(
        request: Request,
        # current_user: typing.Annotated[User, Depends(get_current_active_user)], # Don't lock down list view
        q: str = "",
        page: int = 1,
        pageSize: int = 50,
        deepSearch: bool = False,
    ) -> SearchResultObject[allowed_types]:  # type: ignore
        # TODO add get_list method

        result = await model.get_list(
            q=q, page=page, page_size=pageSize, deep_search=deepSearch
        )

        result.next_page = page + 1 if page + 1 <= result.total_pages else None

        next_url = (
            typing.cast(
                AnyHttpUrl,
                str(
                    request.url.replace_query_params(
                        q=q, page=page + 1, pageSize=pageSize
                    )
                ),
            )
            if page + 1 <= result.total_pages
            else None
        )

        result.next_url = next_url

        result.previous_page = page - 1 if page - 1 >= 1 else None
        result.previous_url = (
            typing.cast(
                AnyHttpUrl,
                str(
                    request.url.replace_query_params(
                        q=q, page=page - 1, pageSize=pageSize
                    )
                ),
            )
            if page - 1 >= 1
            else None
        )
        return result  # type: ignore

    return list


def build_delete_handler(model: type[BaseNode]):
    async def delete(id: ULID) -> None:
        raise HTTPException(status_code=501, detail="Not implemented yet")

    return delete


def build_get_handler(model: type["BaseNode"]):
    async def get(
        id: ULID | AnyHttpUrl,
    ) -> model.HeadView:  # type: ignore
        try:
            result = await model.get_view(id=id)
        except PanglossNotFoundError:
            raise HTTPException(status_code=404, detail="Item not found")
        return result

    return get


def build_create_handler(model: type[BaseNode]):
    async def create(
        background_tasks: BackgroundTasks,
        request: Request,
        entity: model.Create,  # type: ignore
        current_user: typing.Annotated[User, Depends(get_current_active_user)],
    ) -> model.ReferenceView:  # type: ignore
        print(request, entity, current_user)

        entity = typing.cast(CreateBase, entity)
        result, deferred_query = await entity.create(
            username=current_user.username, use_deferred_query=True
        )

        DeferredQueryRunner.run_deferred_create(result.id, deferred_query)

        return result

    return create


def build_get_edit_handler(model: type[BaseNode]):
    async def get_edit(id: ULID) -> model.EditHeadView:  # type: ignore
        try:
            result = await model.get_edit_view(id=id)
        except PanglossNotFoundError:
            raise HTTPException(status_code=404, detail="Item not found")
        return result

    return get_edit


def build_put_edit_handler(model: type[BaseNode]):
    async def put_edit(
        background_tasks: BackgroundTasks,
        id: ULID,
        entity: model.EditHeadSet,  # type: ignore
        current_user: typing.Annotated[User, Depends(get_current_active_user)],
    ) -> SuccessResponse:
        # Check the endpoint id matches the object id!
        if entity.id != id:
            raise HTTPException(status_code=400, detail="Bad request")

        # If a deferred write task on this object is already running,
        # stop it
        DeferredQueryRunner.stop_deferred(instance_id=id)

        try:
            # Do the update, and get deferred update query
            deferred_query = await entity.update(
                username=current_user.username, use_deferred_query=True
            )
        except PanglossNotFoundError:
            raise HTTPException(status_code=404, detail="Item not found")

        # Run the deferred update query
        DeferredQueryRunner.run_deferred_update(id, deferred_query)
        return SuccessResponse(detail="Update successful")

    return put_edit


def setup_api_routes(_app: FastAPI, settings: "BaseSettings") -> FastAPI:
    api_router = APIRouter(prefix="/api")
    for model in sorted(
        ModelManager.base_models.values(), key=lambda model: model.__name__
    ):
        router = APIRouter(
            prefix=f"/{model.__name__}",
            tags=[
                f"{pascalize(str(model.__module__).replace('.models', ''))}.{model.__name__}"
            ],
        )

        router.add_api_route(
            "/",
            endpoint=build_list_handler(model),
            methods={"get"},
            name=f"{model.__name__}.Index",
            operation_id=f"{model.__name__}Index",
        )

        if not model._meta.abstract and model._meta.view:
            router.add_api_route(
                "/{id}",
                endpoint=build_get_handler(model),
                name=f"{model.__name__}.Get",
                operation_id=f"{model.__name__}Get",
            )

            if model.Meta.create:
                router.add_api_route(
                    "/new",
                    endpoint=build_create_handler(model),
                    methods=["post"],
                    name=f"{model.__name__}.Create",
                    operation_id=f"{model.__name__}Create",
                )

            if model.Meta.edit:
                router.add_api_route(
                    "/{id}/edit",
                    endpoint=build_get_edit_handler(model),
                    methods={"get"},
                    name=f"{model.__name__}.Edit.Get",
                    operation_id=f"{model.__name__}EditGet",
                )

                router.add_api_route(
                    "/{id}/edit",
                    endpoint=build_put_edit_handler(model),
                    methods={"put"},
                    name=f"{model.__name__}.Edit.Put",
                    operation_id=f"{model.__name__}EditPut",
                )

            if model.Meta.delete:
                router.add_api_route(
                    "/{id}",
                    endpoint=build_delete_handler(model),
                    methods={"delete"},
                    name=f"{model.__name__}.Delete",
                )

        api_router.include_router(router)
    _app.include_router(api_router)
    return _app

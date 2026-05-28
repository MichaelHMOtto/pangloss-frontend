import importlib.util
import os
import sys
from functools import wraps
from typing import (
    Awaitable,
    Callable,
    NotRequired,
    Optional,
    TypedDict,
    Union,
    overload,
)

import typer

from pangloss.exceptions import PanglossInitialisationError
from pangloss.neo4j.database import Database


def import_project_file_of_name(folder_name: str, file_name: str):
    sys.path.append(os.getcwd())

    MODULE_PATH = os.path.join(folder_name, file_name)
    MODULE_NAME = folder_name
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)

    if spec and spec.loader:
        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            p = importlib.import_module(folder_name, package=folder_name)
        except FileNotFoundError:
            return None
        return p


def get_project_settings(project_name: str):
    p = import_project_file_of_name(folder_name=project_name, file_name="settings.py")

    if not p:
        raise PanglossInitialisationError(f'Project "{project_name}" not found"')
    return getattr(p, "settings")


def get_app_clis(app_name: str) -> list[typer.Typer]:
    p = import_project_file_of_name(folder_name=app_name, file_name="cli.py")
    if p:
        clis = []
        for key, value in p.__dict__.items():
            if isinstance(value, typer.Typer):
                clis.append(value)
        return clis
    return []


def initialise_pangloss_application(settings):
    Database.initialise_default_database(settings)


class InitialisationTaskRegistryItem(TypedDict):
    name: str
    function: Union[Callable[[], Awaitable[None]], Callable[[], None]]
    run_in_dev: NotRequired[bool]
    dev_only: NotRequired[bool]


InitalisationTaskRegistery: list[InitialisationTaskRegistryItem] = []


@overload
def initialisation_task(
    func: Callable[[], Awaitable[None]],
) -> Callable[[], Awaitable[None]]: ...


@overload
def initialisation_task(
    func: Callable[[], None],
) -> Callable[[], None]: ...


@overload
def initialisation_task(
    *, run_in_dev: bool = False, dev_only: bool = False
) -> (
    Callable[[Callable[[], None]], Callable[[], None]]
    | Callable[[Callable[[], Awaitable[None]]], Callable[[], Awaitable[None]]]
): ...


def initialisation_task(
    func: Optional[Union[Callable[[], Awaitable[None]], Callable[[], None]]] = None,
    *,
    run_in_dev: bool = False,
    dev_only: bool = False,
) -> Union[
    Callable[[Callable[[], Awaitable[None]]], Callable[[], Awaitable[None]]],
    Callable[[], Awaitable[None]],
    Callable[[Callable[[], None]], Callable[[], None]],
    Callable[[], None],
]:
    """
    Registers a synchronous or asynchronous task to be run at startup: NOT IMPLEMENTED YET
    """

    # Without arguments `func` is passed directly to the decorator
    if func is not None:
        if not callable(func):
            raise TypeError("Not a callable. Did you use a non-keyword argument?")
        InitalisationTaskRegistery.append(
            {
                "name": func.__name__,
                "function": wraps(func)(func),
                "run_in_dev": run_in_dev,
            }
        )
        return wraps(func)

    # With arguments, we need to return a function that accepts the function
    def decorator(func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        InitalisationTaskRegistery.append(
            {
                "name": func.__name__,
                "function": wraps(func)(func),
                "run_in_dev": run_in_dev,
            }
        )
        return wraps(func)(func)

    return decorator

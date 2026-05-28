import subprocess
import typing
from pathlib import Path

import typer
from rich import print
from rich.panel import Panel

from pangloss.cli.create import create_cli_app

# from pangloss.model_setup.model_manager import ModelManager
from pangloss.cli.users import user_cli
from pangloss.cli.utils import get_project_path
from pangloss.exceptions import PanglossInitialisationError

# from pangloss.types_generation import type_generation_cli
# from pangloss.translation import translation_cli
from pangloss.indexes import install_indexes_and_constraints
from pangloss.initialisation import get_project_settings
from pangloss.neo4j.database import Database

cli_app = typer.Typer(
    add_completion=False,
    help="Pangloss CLI",
    name="Pangloss CLI",
)

cli_app.add_typer(user_cli, name="users")
cli_app.add_typer(create_cli_app, name="create")


Project = typing.Annotated[
    Path, typer.Option(exists=True, help="The path of the project to run")
]


def start_project_settings(project_path):
    if not project_path:
        raise PanglossInitialisationError(
            "No Pangloss Project specified in pyproject.toml or via --project flag"
        )
    try:
        settings = get_project_settings(project_path)
    except PanglossInitialisationError:
        print("Cannot find settings")

    try:
        Database.initialise_default_database(settings)
        for app in settings.INSTALLED_APPS:
            try:
                __import__(app)
            except Exception as e:
                print("Error import app", app, e)
            try:
                __import__(f"{app}.models")
            except Exception as e:
                print(e)
            try:
                __import__(f"{app}.background_tasks")
            except ModuleNotFoundError:
                # raise PanglossInitialisationError(f"{app} background tasks not found")
                pass
            try:
                m = __import__(f"{app}.cli")
                typer_objects = [
                    v for k, v in m.cli.__dict__.items() if isinstance(v, typer.Typer)
                ]
                for typer_object in typer_objects:
                    cli_app.add_typer(typer_object, name=typer_object.info.name)
            except AttributeError as e:
                print("Error importing app: AttributeError", e)
            except ModuleNotFoundError as e:
                print("Error importing app: ModuleNotFoundError", e)
            except Exception as e:
                raise PanglossInitialisationError(f"Cannot install CLI for {app}, {e}")
    except AttributeError as e:
        print("err", e)

    except PanglossInitialisationError as e:
        print("Cannot start app", e)


@cli_app.command(name="dev", help="Starts development server")
def dev(
    Project=typing.Annotated[
        Path, typer.Option(exists=False, help="The path of the project to run")
    ],
):
    project_path = get_project_path()

    start_project_settings(project_path)
    settings = get_project_settings(str(project_path))
    reload_watch_list = []  # ["--reload-dir", project_path]

    for installed_app in settings.INSTALLED_APPS:
        m = __import__(installed_app)

        reload_watch_list.append("--reload-dir")
        reload_watch_list.append(m.__path__[0])

    panel = Panel(
        (
            f"Autoreloading on!\n\n   Watching project: [bold green]{str(project_path)}[/bold green]\n   "
            f"Watching installed apps: {', '.join(f'[bold blue]{a}[/bold blue]' for a in settings.INSTALLED_APPS)}"
        ),
        title="📜 Starting Pangloss development server!",
        subtitle="(tally ho!)",
        subtitle_align="right",
    )
    print("\n\n", panel, "\n\n")

    pp = ".".join(Path(typing.cast(str, project_path)).parts)

    sc_command = [
        "uvicorn",
        f"{str(pp)}.main:app",
        "--lifespan",
        "on",
        "--reload",
        *reload_watch_list,
    ]
    subprocess.call(sc_command)


@cli_app.command(name="run", help="Starts development server")
def run(
    Project=typing.Annotated[
        Path, typer.Option(exists=False, help="The path of the project to run")
    ],
):
    project_path = get_project_path()

    start_project_settings(project_path)
    settings = get_project_settings(str(project_path))
    # reload_watch_list = []  # ["--reload-dir", project_path]

    for installed_app in settings.INSTALLED_APPS:
        m = __import__(installed_app)

        # reload_watch_list.append("--reload-dir")
        # reload_watch_list.append(m.__path__[0])

    pp = ".".join(Path(typing.cast(str, project_path)).parts)

    sc_command = [
        "uvicorn",
        f"{str(pp)}.main:app",
    ]
    subprocess.call(sc_command)


@cli_app.command()
def setup_database():
    project_path = get_project_path()
    start_project_settings(project_path)
    install_indexes_and_constraints()


project_path = get_project_path()


def cli():
    """Initialises the Typer-based CLI by checking installed app folders
    for a cli.py file and finding Typer apps inside."""
    try:
        start_project_settings(project_path)
    except Exception:
        pass
    # Ugly hack that supresses all cli errors. Need some way to mark whether a
    # cli app needs a project or not!
    return cli_app()

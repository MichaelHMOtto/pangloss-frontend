import os
import typing

import typer
from cookiecutter.exceptions import OutputDirExistsException
from cookiecutter.main import cookiecutter
from rich import print
from rich.panel import Panel

create_cli_app = typer.Typer(
    add_completion=False,
    help="Pangloss CLI",
    name="Pangloss CLI",
)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")


@create_cli_app.command(name="app", help="Create new project")
def create_app(app_name: typing.Annotated[str, typer.Argument()]):
    context = {"folder_name": app_name}
    try:
        cookiecutter(
            os.path.join(TEMPLATES_DIR, "app"),
            extra_context=context,
            no_input=True,
        )
    except OutputDirExistsException:
        print(
            "\n",
            Panel(
                f"[bold red]App creation failed:[/bold red] Folder [bold blue]{context['folder_name']}[/bold blue] already exists.",
                title="Creating Pangloss app",
                subtitle="😡",
                subtitle_align="right",
            ),
            "\n",
        )
    else:
        print(
            "\n",
            Panel(
                (
                    f"[bold green]App successfully created:[/bold green] Pangloss app [bold blue]{context['folder_name']}[/bold blue] created successfully!"
                    f'\n\nGo to your project [blue]settings.py[/blue] and add [blue]"{context["folder_name"]}"[/blue] to [blue]Settings.INSTALLED_APPS[/blue]:'
                    f"\n\nThen go to [blue]{context['folder_name']}/models.py[/blue] to add some models"
                ),
                title="Creating Pangloss project",
                subtitle="🍹",
                subtitle_align="right",
            ),
            "\n",
        )


@create_cli_app.command(name="project", help="Create new project")
def create_project(project_name: typing.Annotated[str, typer.Argument()]):
    context = {"folder_name": project_name}
    try:
        cookiecutter(
            os.path.join(TEMPLATES_DIR, "project"),
            extra_context=context,
            no_input=True,
        )
    except OutputDirExistsException:
        print(
            "\n",
            Panel(
                f"[bold red]Project creation failed:[/bold red] Folder [bold blue]{context['folder_name']}[/bold blue] already exists.",
                title="Creating Pangloss project",
                subtitle="😡",
                subtitle_align="right",
            ),
            "\n",
        )
    else:
        print(
            "\n",
            Panel(
                (
                    f"[bold green]Project successfully created:[/bold green] Pangloss project [bold blue]{context['folder_name']}[/bold blue] created successfully!"
                    f"\n\nGo to [blue]{context['folder_name']}/settings.py[/blue] to configure the database"
                    f"\n\nThen run [deep_pink4]pangloss run {context['folder_name']}[/deep_pink4] to run the development server"
                ),
                title="Creating Pangloss project",
                subtitle="🍹",
                subtitle_align="right",
            ),
            "\n",
        )

import asyncio

import typer
from rich import print

from pangloss.exceptions import PanglossUserError
from pangloss.users.utils import create_user, get_email

user_cli = typer.Typer(name="users")


@user_cli.command(help="Add new user")
def create():
    # initialise_pangloss_application(get_project_settings(str(project)))

    print("[green bold]Creating a new user[/green bold]")
    username = typer.prompt("Username", type=str)

    _, email = get_email()

    password = str(
        typer.prompt(
            "Password",
            type=str,
            confirmation_prompt="Repeat password to confirm",
            hide_input=True,
        )
    )

    admin = typer.confirm("Make admin?")

    try:
        asyncio.run(
            create_user(
                username=username,
                email=email,
                password=password.strip(),
                admin=admin,
            )
        )

    except PanglossUserError as e:
        raise e

    print(f"\n[green bold]Done! Created user '{username}' [/green bold]")

import pathlib
import sys

import tomllib


def get_project_path():
    project_path = None
    if "--project" in sys.argv:
        project_path = sys.argv[sys.argv.index("--project") + 1]
    else:
        try:
            f = pathlib.Path("pyproject.toml")
            if f.is_file:
                data = f.read_text()
                data = tomllib.loads(data)
                project_path = data["tool"]["pangloss"]["config"]["project"]
        except Exception:
            pass
    return project_path

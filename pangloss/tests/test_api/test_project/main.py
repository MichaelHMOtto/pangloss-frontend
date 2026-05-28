from pangloss.application import get_application
from tests.test_api.test_project.settings import settings

app = get_application(settings=settings)


@app.get("/")
def index():
    return {"Hello": "World"}

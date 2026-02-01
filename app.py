from pathlib import Path

from litestar import Litestar, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.response import Redirect, Template
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from modules.discord_bot import bot_start_lifespan
from modules.types import Party
from modules.buzzer import buzzer_router
from modules.host import host_router


@get("/favicon.ico")
async def favicon() -> None:
    return None


@get("/")
async def index(request: Request) -> Template | Redirect:
    party_id = request.cookies.get("party")
    user_id = request.cookies.get("user")
    if party_id and user_id:
        party: Party = app.state.parties.get(party_id)
        if party and user_id in party.lost_connections:
            print(party.lost_connections)
            return Redirect(f"/buzzer/{party.id}")
    return Template("index.html")


app = Litestar(
    route_handlers=[
        index,
        favicon,
        buzzer_router,
        host_router,
        create_static_files_router(path="static", directories=[Path("static")]),
    ],
    lifespan=[bot_start_lifespan],
    template_config=TemplateConfig(
        directory=Path("templates"),
        engine=JinjaTemplateEngine,
    ),
    openapi_config=None,
)
app.state.parties = {}

from litestar import Router, Request, get, websocket
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.response import Redirect, Template

from modules.types import Party, PlayerConnection


@websocket("ws", websocket_class=PlayerConnection)
async def host_config_ws(socket: PlayerConnection) -> None:
    party: Party = socket.app.state.parties.get(socket.cookies.get("party", ""), None)
    if party:
        async with party.host_connection(socket):
            while True:
                msg = await socket.receive_json()
                if msg["event"] == "RESET":
                    await party.reset_buzzers()
                elif msg["event"] == "TOGGLE_LOCK":
                    party.locked = not party.locked
                    await party.update_buzzers()
                elif msg["event"] == "PROMPT_CHOICES":
                    await party.prompt_multiple_choice(
                        [m.strip() for m in msg["choices"].strip().splitlines()]
                    )
                elif msg["event"] == "CLEAR_MC":
                    party.available_choices = None
                    party.show_choices = False
                    for c in party.all_connections:
                        c.game_data.choice = None
                    await party.update_buzzers()
                elif msg["event"] == "END_MC":
                    await party.end_multiple_choice()
    else:
        print("No Party.")
        raise HTTPException(status_code=400, detail="No Party")


@get("/")
async def no_buzzer(request: Request) -> Template | Redirect:
    error_code = request.query_params.get("error")
    error = None
    if error_code == "1":
        error = "The provided party code is invalid."
    elif error_code == "2":
        error = "To admin the board, please click the admin button on discord."
    elif error_code == "3":
        error = "You are not a member or host of this board."
    elif error_code == "4":
        error = "Party has ended."

    elif error_code:
        error = "An unknown error has occurred."
    if error_code:
        return Template("error.html", context={"error": error})
    else:
        return Redirect("/")


@get("/{buzzer_id:str}")
async def host(request: Request, buzzer_id: str) -> Template | Redirect:
    user = request.query_params.get("user")
    if user:
        return Redirect(f"/host/{buzzer_id}", cookies=[Cookie(key="user", value=user)])

    user = user or request.cookies.get("user")

    party: Party = request.app.state.parties.get(buzzer_id)

    if not party:
        return Redirect("/host", query_params={"error": "1"})

    if not user:
        return Redirect("/host", query_params={"error": "2"})

    if user != party.host:
        if user in party.users:
            return Redirect(f"/buzzer/{buzzer_id}")

        return Redirect("/buzzer", query_params={"error": "3"})

    return Template(
        "host.html",
        cookies=[Cookie(key="party", value=buzzer_id), Cookie(key="user", value=user)],
    )


host_router = Router(path="/host", route_handlers=[host, no_buzzer, host_config_ws])

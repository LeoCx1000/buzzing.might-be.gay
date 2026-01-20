from litestar import Router, Request, get, websocket
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.response import Redirect, Template

from modules.types import Party, PlayerConnection


@websocket("/ws", websocket_class=PlayerConnection)
async def listen_for_buzzes(socket: PlayerConnection) -> None:
    party: Party = socket.app.state.parties.get(socket.cookies.get("party", ""), None)
    if party:
        async with party.connection(socket):
            await party.update_buzzers()
            while not socket.leaving:
                msg = await socket.receive_json()
                if msg["event"] == "BUZZ":
                    party.player_buzz(socket)
                if msg["event"] == "LEAVE":
                    socket.leaving = True
                    await socket.close(code=1013, reason="You left.")
                    break
                if msg["event"] == "PONG":
                    socket.received_rtt_pong(msg["id"])

    else:
        print("No Party.")
        raise HTTPException(status_code=400, detail="idiot")


@get("/")
async def no_buzzer(request: Request) -> Template | Redirect:
    error_code = request.query_params.get("error")
    print(error_code, "code")
    error = None
    if error_code == "1":
        error = "The provided party code is invalid."
    elif error_code == "2":
        error = "To join, please click the button provided by the discord bot."
    elif error_code == "3":
        error = "The user identifier provided is invalid. You may have been kicked from the buzzer session."
    elif error_code == "4":
        error = "The game was closed by the host."
    elif error_code:
        error = "An unknown error has occurred."

    print(error)
    if error:
        return Template("error.html", context={"error": error})
    else:
        return Redirect("/")


@get("/{buzzer_id:str}")
async def buzzer(request: Request, buzzer_id: str) -> Template | Redirect:
    print("got this!")
    user = request.query_params.get("user")
    if user:
        return Redirect(
            f"/buzzer/{buzzer_id}", cookies=[Cookie(key="user", value=user)]
        )

    user = user or request.cookies.get("user")

    party = request.app.state.parties.get(buzzer_id)

    if not party:
        return Redirect("/buzzer", query_params={"error": "1"})

    if not user:
        return Redirect("/buzzer", query_params={"error": "2"})

    elif user not in party.users:
        return Redirect("/buzzer", query_params={"error": "3"})

    return Template(
        "buzzer.html",
        cookies=[Cookie(key="party", value=buzzer_id), Cookie(key="user", value=user)],
    )


buzzer_router = Router(
    path="/buzzer", route_handlers=[buzzer, no_buzzer, listen_for_buzzes]
)

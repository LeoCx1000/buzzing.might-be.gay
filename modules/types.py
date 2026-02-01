import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from secrets import token_urlsafe
from statistics import mean
from time import monotonic

import discord
from litestar import WebSocket as BaseWebSocket, Litestar
from litestar import status_codes
from litestar.exceptions import WebSocketDisconnect, WebSocketException


class CrossConnectionData:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.buzzed: bool = False
        self.buzzed_at: float = 0.0
        self.leaving: bool = False
        self.discord_user: discord.abc.User
        self.choice: str | None = None


class PlayerConnection(BaseWebSocket):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rtt_times: deque[float] = deque(maxlen=30)
        self._rtt: float = 0.0
        self.sent_times: dict[str, float] = {}

        user_id = self.cookies.get("user")
        if not user_id:
            raise WebSocketException(detail="Unknown User")

        self.game_data = CrossConnectionData(user_id)

    @property
    def rtt(self) -> float:
        return self._rtt

    @rtt.setter
    def rtt(self, new: float):
        self.rtt_times.append(new)
        self._rtt = mean(self.rtt_times)

    async def send_rtt_pings(self):
        while True:
            token = token_urlsafe(8)
            now = monotonic()
            await self.send_json({"event": "PING", "id": token})
            self.sent_times[token] = now

            # Check if there are any old rtt packages
            to_remove = []
            for token, then in self.sent_times.items():
                if (now - then) > 10:
                    to_remove.append(token)

            for token in to_remove:
                self.sent_times.pop(token, None)

            await asyncio.sleep(2)

    def received_rtt_pong(self, token: str):
        now = monotonic()
        old = self.sent_times.pop(token, None)
        if old:
            self.rtt = now - old


class Party:
    def __init__(self, party_id: str, app: Litestar):
        self.app = app
        self.id = party_id
        self.connections: dict[str, PlayerConnection] = {}
        self.lost_connections: dict[str, PlayerConnection] = {}
        self.users: dict[str, discord.abc.User] = {}
        self.locked: bool = False
        self.host: str | None = None
        self.host_ws: BaseWebSocket | None = None
        self.available_choices: list[str] | None = None
        self.show_choices: bool = False
        self.lost_host_timeout_task: asyncio.Task | None = None

    async def broadcast_to_players(self, message: dict):
        for con in self.connections.values():
            asyncio.create_task(con.send_json(message))
        if self.host_ws:
            asyncio.create_task(self.host_ws.send_json(message))

    def base_user_update_payload(self, sound: bool = False, choices: bool = False):
        return {
            "event": "UPDATE",
            "sound": sound,
            "users": [
                {
                    "name": c.game_data.discord_user.display_name,
                    "avatar": c.game_data.discord_user.display_avatar.url,
                    "buzzed": c.game_data.buzzed,
                    "connected": c.connection_state != "disconnect",
                    "choice": c.game_data.choice if choices else None,
                }
                for c in sorted(
                    self.all_connections,
                    key=lambda c: (c.game_data.buzzed_at == 0.0, c.game_data.buzzed_at),
                )
                if not c.game_data.leaving
            ],
            "t": monotonic(),
            "button_state": "LOCKED" if self.locked else "OPEN",
        }

    async def update_buzzers(self, sound: bool = False):
        payload = self.base_user_update_payload(sound=sound, choices=self.show_choices)

        if self.host_ws:
            asyncio.create_task(
                self.host_ws.send_json(
                    self.base_user_update_payload(sound=sound, choices=True)
                )
            )

        for conn in self.connections.values():
            if not self.locked:
                payload["button_state"] = "BUZZED" if conn.game_data.buzzed else "OPEN"

            if self.available_choices and not conn.game_data.choice:
                payload["choices"] = self.available_choices
            payload["choice"] = conn.game_data.choice

            try:
                await conn.send_json(payload)
            except WebSocketException:
                pass

    @property
    def all_connections(self):
        return [*self.connections.values(), *self.lost_connections.values()]

    async def reset_buzzers(self):
        for conn in self.all_connections:
            conn.game_data.buzzed = False
            conn.game_data.buzzed_at = 0.0
        await self.update_buzzers()

    def player_buzz(self, socket: PlayerConnection):
        print("buzz: RTT", socket.rtt)
        time = monotonic() - min(socket.rtt, 1)
        if not socket.game_data.buzzed and not self.locked:
            socket.game_data.buzzed = True
            socket.game_data.buzzed_at = time
            asyncio.create_task(self.update_buzzers(sound=True))

    async def prompt_multiple_choice(self, choices: list[str]):
        self.available_choices = choices
        self.locked = True
        self.show_choices = False

        for conn in self.all_connections:
            conn.game_data.choice = None

        await self.update_buzzers()
        await self.broadcast_to_players(
            {"event": "MULTIPLE_CHOICE", "choices": choices}
        )

    async def received_mc_answer(self, socket: PlayerConnection, choice: str):
        if not self.available_choices:
            return
        if socket.game_data.choice in self.available_choices:
            return
        if choice not in self.available_choices:
            return
        socket.game_data.choice = choice
        if all(
            c.game_data.choice in self.available_choices
            for c in self.connections.values()
        ):
            self.show_choices = True
        await self.update_buzzers()

    async def end_multiple_choice(self):
        self.show_choices = True
        self.available_choices = None
        await self.broadcast_to_players({"event": "END_MULTIPLE_CHOICE"})
        await self.update_buzzers()

    @asynccontextmanager
    async def connection(self, conn: PlayerConnection):
        conn.game_data.discord_user = self.users[conn.game_data.user_id]
        await conn.accept()
        task = None

        try:
            previous_conn = self.connections.pop(conn.game_data.user_id, None)
            if previous_conn:
                asyncio.create_task(
                    previous_conn.close(
                        code=status_codes.WS_1013_TRY_AGAIN_LATER,
                        reason="Connected from another location.",
                    )
                )
                conn.game_data = previous_conn.game_data

            self.connections[conn.game_data.user_id] = conn

            # Restrore previous state
            old_connection = self.lost_connections.pop(conn.game_data.user_id, None)
            if old_connection:
                conn.game_data = old_connection.game_data

            payload = self.base_user_update_payload()
            if not self.locked:
                payload["button_state"] = "BUZZED" if conn.game_data.buzzed else "OPEN"

            await conn.send_json(payload)
            task = asyncio.create_task(conn.send_rtt_pings())
            yield
        except WebSocketDisconnect:
            pass
        finally:
            self.connections.pop(conn.game_data.user_id, None)
            self.lost_connections[conn.game_data.user_id] = conn

            if conn.game_data.leaving:
                await self.update_buzzers()

            if task:
                task.cancel()

    async def lost_host_connection(self):
        await asyncio.sleep(300)

        self.app.state.parties.pop(self.id, None)

        for conn in self.connections.values():
            try:
                await conn.close()
            except Exception:
                logging.info("Could not close connection")
                pass

    @asynccontextmanager
    async def host_connection(self, conn: BaseWebSocket):
        await conn.accept()
        if self.host_ws:
            try:
                await self.host_ws.close()
            except WebSocketException:
                pass
        if self.lost_host_timeout_task:
            self.lost_host_timeout_task.cancel()
            self.lost_host_timeout_task = None

        try:
            self.host_ws = conn

            payload = self.base_user_update_payload(choices=True)
            await conn.send_json(payload)
            yield
        except WebSocketDisconnect:
            self.lost_host_timeout_task = asyncio.create_task(
                self.lost_host_connection()
            )
            pass

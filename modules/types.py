import asyncio
from collections import deque
from contextlib import asynccontextmanager
from secrets import token_urlsafe
from statistics import mean
from time import monotonic

import discord
from litestar import WebSocket as BaseWebSocket
from litestar.exceptions import WebSocketDisconnect, WebSocketException
from litestar import status_codes


class PlayerConnection(BaseWebSocket):
    _discord_user: discord.abc.User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rtt_times: deque[float] = deque(maxlen=30)
        self._rtt: float = 0.0
        self.sent_times: dict[str, float] = {}
        user_id = self.cookies.get("user")
        if not user_id:
            raise WebSocketException(detail="Unknown User")
        self.user_id = user_id
        self.buzzed: bool = False
        self.buzzed_at: float = 0.0
        self.leaving: bool = False

    @property
    def user(self):
        return self._discord_user

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
    def __init__(self, party_id: str):
        self.id = party_id
        self.connections: dict[str, PlayerConnection] = {}
        self.lost_connections: dict[str, PlayerConnection] = {}
        self.users: dict[str, discord.abc.User] = {}
        self.locked: bool = False
        self.host: str | None = None
        self.host_ws: BaseWebSocket | None = None

    async def broadcast_to_players(self, message: dict):
        for con in self.connections.values():
            asyncio.create_task(con.send_json(message))
        if self.host_ws:
            asyncio.create_task(self.host_ws.send_json(message))

    def base_user_update_payload(self, sound: bool = False):
        return {
            "event": "UPDATE",
            "sound": sound,
            "users": [
                {
                    "name": c.user.display_name,
                    "avatar": c.user.display_avatar.url,
                    "buzzed": c.buzzed,
                }
                for c in sorted(
                    [*self.connections.values(), *self.lost_connections.values()],
                    key=lambda c: (c.buzzed_at == 0.0, c.buzzed_at),
                )
                if not c.leaving
            ],
            "t": monotonic(),
            "button_state": "LOCKED" if self.locked else "OPEN",
        }

    async def update_buzzers(self, sound: bool = False):
        payload = self.base_user_update_payload(sound=sound)

        if self.host_ws:
            asyncio.create_task(self.host_ws.send_json(payload))

        for conn in self.connections.values():
            if not self.locked:
                payload["button_state"] = "BUZZED" if conn.buzzed else "OPEN"

            try:
                await conn.send_json(payload)
            except WebSocketException:
                pass

    async def reset_buzzers(self):
        for conn in [*self.connections.values(), *self.lost_connections.values()]:
            conn.buzzed = False
            conn.buzzed_at = 0.0
        await self.update_buzzers()

    def player_buzz(self, socket: PlayerConnection):
        time = monotonic() - socket.rtt
        if not socket.buzzed and not self.locked:
            socket.buzzed = True
            socket.buzzed_at = time
            asyncio.create_task(self.update_buzzers(sound=True))

    @asynccontextmanager
    async def connection(self, conn: PlayerConnection):
        conn._discord_user = self.users[conn.user_id]
        await conn.accept()
        task = None

        try:
            previous_conn = self.connections.pop(conn.user_id, None)
            if previous_conn:
                asyncio.create_task(
                    previous_conn.close(
                        code=status_codes.WS_1013_TRY_AGAIN_LATER,
                        reason="Connected from another location.",
                    )
                )

            self.connections[conn.user_id] = conn

            # Restrore previous state
            old_connection = self.lost_connections.pop(conn.user_id, None)
            if old_connection:
                conn.buzzed = old_connection.buzzed
                conn.buzzed_at = old_connection.buzzed_at

            payload = self.base_user_update_payload()
            if not self.locked:
                payload["button_state"] = "BUZZED" if conn.buzzed else "OPEN"

            await conn.send_json(payload)
            task = asyncio.create_task(conn.send_rtt_pings())
            yield
        except WebSocketDisconnect:
            pass
        finally:
            self.connections.pop(conn.user_id, None)
            self.lost_connections[conn.user_id] = conn

            if conn.leaving:
                await self.update_buzzers()

            if task:
                task.cancel()

    @asynccontextmanager
    async def host_connection(self, conn: BaseWebSocket):
        await conn.accept()
        if self.host_ws:
            try:
                await self.host_ws.close()
            except WebSocketException:
                pass
        try:
            self.host_ws = conn

            payload = self.base_user_update_payload()
            await conn.send_json(payload)

            yield
        except WebSocketDisconnect:
            pass
        finally:
            self.host_ws = conn

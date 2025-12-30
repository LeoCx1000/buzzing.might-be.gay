from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from secrets import token_urlsafe

import discord
from discord import app_commands
from litestar import Litestar

from config import BOT_TOKEN, BASE_URL

from .types import Party


class RoomInitiator(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.none())
        self._app: Litestar | None = None
        self.tree = app_commands.CommandTree(
            self,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )

    @property
    def app(self):
        if not self._app:
            raise RuntimeError("Bot has no app bound to it")
        return self._app


client = RoomInitiator()

buzzer_cmd = app_commands.Group(
    name="buzzer",
    description="Managing buzzer sessions",
)
client.tree.add_command(buzzer_cmd)


class JoinRoomView(discord.ui.View):
    def __init__(self, owner: discord.abc.User, party: Party, board_name: str | None):
        super().__init__(timeout=None)
        manage_url = f"{BASE_URL}/host/{party.id}"
        self.embed = discord.Embed(
            title="Buzzer Round",
            description=f"Hosted by {owner.mention}"
            + f"\nParty ID: `{party.id}` [manage](<{manage_url}>)"
            + (f"\nBoard Name:{board_name}" if board_name else ""),
        )
        self.owner = owner
        self.board_name = board_name
        self.party = party

    @discord.ui.button(label="Join", style=discord.ButtonStyle.blurple)
    async def join_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Sends an ephemeral message with a user-specific join link"""
        codes = [c for c, u in self.party.users.items() if u.id == interaction.user.id]
        code = codes[0] if codes else token_urlsafe(16)
        self.party.users[code] = interaction.user
        await interaction.response.send_message(
            f"{interaction.user.mention} join the buzzer here:"
            f"\n<{BASE_URL}/buzzer/{self.party.id}?user={code}>"
            "\n## DO NOT share this link with anyone.\nEach participant must click join individually.",
            ephemeral=True,
        )


@buzzer_cmd.command(name="create")
@app_commands.describe(board_name="The name of the board")
async def buzzer_create(interaction: discord.Interaction, board_name: str | None):
    """Creates a new buzzer session."""
    room_id = token_urlsafe(6)
    client.app.state.parties[room_id] = party = Party(room_id)
    view = JoinRoomView(owner=interaction.user, party=party, board_name=board_name)
    await interaction.response.send_message(view=view, embed=view.embed)

    code = token_urlsafe(16)
    party.users[code] = interaction.user

    party.host = code

    await interaction.followup.send(
        f"{interaction.user.mention} manage your buzzer here:"
        f"\n<{BASE_URL}/host/{party.id}?user={code}>"
        "\n## You must click this link first, but if you lose the tab you can click on manage on the main message."
        "\nAlso do not share this link with anyone.",
        ephemeral=True,
    )


@asynccontextmanager
async def bot_start_lifespan(app: Litestar):
    client._app = app
    async with client:
        asyncio.create_task(client.start(BOT_TOKEN))
        await client.wait_until_ready()
        yield

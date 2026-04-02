import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import BOT_TOKEN, GUILD_ID
from bot.db import init_db
from bot.logging_config import setup_logging
from bot.cogs.admin import AdminCog
from bot.cogs.hosts import HostsCog
from bot.cogs.network import NetworkCog
from bot.cogs.power import PowerCog
from bot.cogs.proxmox import ProxmoxCog
from bot.cogs.tools import ToolsCog

logger = logging.getLogger(__name__)


class HomelabBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.start_time: float = time.time()

    async def setup_hook(self) -> None:
        await init_db()
        await self.add_cog(HostsCog(self))
        await self.add_cog(NetworkCog(self))
        await self.add_cog(PowerCog(self))
        await self.add_cog(ToolsCog(self))
        await self.add_cog(ProxmoxCog(self))
        await self.add_cog(AdminCog(self))
        logger.info("All cogs loaded successfully")
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands synced to guild %s", GUILD_ID)

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
    else:
        logger.error("Unhandled command error: %s", error, exc_info=True)
        msg = "An unexpected error occurred. Please try again later."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass


def main() -> None:
    setup_logging()
    bot = HomelabBot()
    bot.tree.on_error = on_app_command_error
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()

import logging
import time

import nextcord
from nextcord.ext import commands
from nextcord.ext.application_checks import ApplicationCheckFailure

from bot.config import BOT_TOKEN
from bot.db import init_db
from bot.logging_config import setup_logging
from bot.cogs.admin import AdminCog
from bot.cogs.hosts import HostsCog
from bot.cogs.network import NetworkCog
from bot.cogs.power import PowerCog
from bot.cogs.tools import ToolsCog

logger = logging.getLogger(__name__)


class HomelabBot(commands.Bot):
    def __init__(self) -> None:
        intents = nextcord.Intents.default()
        super().__init__(intents=intents)
        self.start_time: float = time.time()

    async def setup_hook(self) -> None:
        await init_db()
        self.add_cog(HostsCog(self))
        self.add_cog(NetworkCog(self))
        self.add_cog(PowerCog(self))
        self.add_cog(ToolsCog(self))
        self.add_cog(AdminCog(self))
        logger.info("All cogs loaded successfully")

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))

    async def on_application_command_error(
        self, interaction: nextcord.Interaction, error: Exception
    ) -> None:
        if isinstance(error, ApplicationCheckFailure):
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
    # log_handler=None tells nextcord not to configure its own logging,
    # since we've already set up our own handlers above.
    bot.run(BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

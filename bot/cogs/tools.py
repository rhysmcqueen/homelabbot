import asyncio
import logging
from typing import Optional

import nextcord
from nextcord.ext import commands

from bot.config import GUILD_ID

logger = logging.getLogger(__name__)

MAX_TIMER_MINUTES = 60


class ToolsCog(commands.Cog, name="Tools"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /hello
    # ------------------------------------------------------------------

    @nextcord.slash_command(
        name="hello",
        description="Health check — confirm the bot is up and responding",
        guild_ids=[GUILD_ID],
    )
    async def hello(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(
            f"Hello, {interaction.user.mention}! I'm alive and ready.",
            ephemeral=True,
        )
        logger.info("%s used /hello", interaction.user)

    # ------------------------------------------------------------------
    # /timer
    # ------------------------------------------------------------------

    @nextcord.slash_command(
        name="timer",
        description=f"Set a countdown timer (1–{MAX_TIMER_MINUTES} minutes)",
        guild_ids=[GUILD_ID],
    )
    async def timer(
        self,
        interaction: nextcord.Interaction,
        minutes: int = nextcord.SlashOption(
            description=f"Minutes to wait (1–{MAX_TIMER_MINUTES})",
            min_value=1,
            max_value=MAX_TIMER_MINUTES,
        ),
        label: Optional[str] = nextcord.SlashOption(
            description="Optional label for this timer",
            required=False,
        ),
    ):
        tag = f" — *{label}*" if label else ""
        await interaction.response.send_message(
            f"Timer set for **{minutes} minute(s)**{tag}. "
            f"I'll mention you when it's done."
        )
        logger.info(
            "%s set a %d-minute timer%s",
            interaction.user,
            minutes,
            f" ({label})" if label else "",
        )

        await asyncio.sleep(minutes * 60)

        try:
            await interaction.followup.send(
                f"{interaction.user.mention} Your **{minutes}-minute** timer is up!{tag}"
            )
        except Exception as exc:
            logger.warning(
                "Could not deliver timer notification to %s: %s", interaction.user, exc
            )

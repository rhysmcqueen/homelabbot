import logging

import discord
from discord import app_commands

from bot.config import MANAGEMENT_ROLE_ID, OWNER_ID

logger = logging.getLogger(__name__)


def _log_denied(interaction: discord.Interaction, required: str) -> None:
    cmd = interaction.command.name if interaction.command else "unknown"
    logger.warning(
        "Permission denied (%s required): %s (ID: %s) attempted /%s in guild %s",
        required,
        interaction.user,
        interaction.user.id,
        cmd,
        interaction.guild_id,
    )


def is_owner():
    """Restrict command to the bot owner only."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        _log_denied(interaction, "owner")
        return False

    return app_commands.check(predicate)


def is_management():
    """Restrict command to the bot owner or members with the management role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        if interaction.guild:
            role_ids = {r.id for r in interaction.user.roles}
            if MANAGEMENT_ROLE_ID in role_ids:
                return True
        _log_denied(interaction, "management")
        return False

    return app_commands.check(predicate)

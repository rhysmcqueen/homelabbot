import logging
import platform
import sys
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot import __version__
from bot.config import (
    DATABASE_PATH,
    GUILD_ID,
    LOG_LEVEL,
    MANAGEMENT_ROLE_ID,
    OWNER_ID,
)
from bot.db import get_host_count
from bot.permissions import is_owner

logger = logging.getLogger(__name__)


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /botinfo
    # ------------------------------------------------------------------

    @app_commands.command(
        name="botinfo",
        description="Show bot status, uptime, and statistics",
    )
    async def botinfo(self, interaction: discord.Interaction):
        await interaction.response.defer()

        uptime = _format_uptime(time.time() - self.bot.start_time)
        host_count = await get_host_count()

        try:
            import discord as _dc
            dc_version = _dc.__version__
        except Exception:
            dc_version = "unknown"

        embed = discord.Embed(
            title="HomelabBot",
            description="A Discord bot for managing your homelab infrastructure.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Version", value=f"`{__version__}`", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="Hosts in DB", value=str(host_count), inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Python", value=f"`{sys.version.split()[0]}`", inline=True
        )
        embed.add_field(name="discord.py", value=f"`{dc_version}`", inline=True)
        embed.set_footer(
            text=f"Running on {platform.system()} {platform.release()}"
        )
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /setting
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setting",
        description="View current bot configuration — owner only",
    )
    @is_owner()
    async def setting(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="Bot Configuration",
            description="Current runtime configuration. "
            "To change values, update `.env` and restart the bot.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Guild ID", value=f"`{interaction.guild_id}`", inline=True)
        embed.add_field(name="Owner ID", value=f"`{OWNER_ID}`", inline=True)
        embed.add_field(
            name="Management Role ID", value=f"`{MANAGEMENT_ROLE_ID}`", inline=True
        )
        embed.add_field(name="Log Level", value=f"`{LOG_LEVEL}`", inline=True)
        embed.add_field(name="Database", value=f"`{DATABASE_PATH}`", inline=True)
        embed.add_field(name="Version", value=f"`{__version__}`", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("%s viewed bot settings", interaction.user)

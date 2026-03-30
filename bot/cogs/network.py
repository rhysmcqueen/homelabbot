import asyncio
import logging
import platform
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from wakeonlan import send_magic_packet

from bot.db import get_all_hosts, get_host
from bot.permissions import is_management

logger = logging.getLogger(__name__)


async def _ping(ip: str, count: int = 4) -> tuple[bool, str]:
    """Run a system ping and return (reachable, summary_line)."""
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", str(count), ip]
    else:
        cmd = ["ping", "-c", str(count), "-W", "2", ip]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode(errors="replace")
        success = proc.returncode == 0

        # Pull the statistics summary line out of the output
        summary = ""
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped and any(
                kw in stripped.lower()
                for kw in ("packet", "transmitted", "received", "loss", "min/avg/max")
            ):
                summary = stripped
                break

        return success, summary or output.strip()[-200:]
    except asyncio.TimeoutError:
        return False, "Ping timed out after 15 seconds."
    except FileNotFoundError:
        return False, "ping command not found on this host."
    except Exception as exc:
        return False, f"Error: {exc}"


class NetworkCog(commands.Cog, name="Network"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /ping
    # ------------------------------------------------------------------

    @app_commands.command(
        name="ping", description="Ping a host to check reachability",
    )
    @app_commands.describe(host="Host name from DB, or a raw IP address")
    async def ping(
        self,
        interaction: discord.Interaction,
        host: str,
    ):
        await interaction.response.defer()

        host_record = await get_host(host)
        ip = host_record["ip"] if host_record else host
        display_name = host_record["name"] if host_record else host

        logger.info("%s pinged %s (%s)", interaction.user, display_name, ip)

        success, summary = await _ping(ip)
        color = discord.Color.green() if success else discord.Color.red()
        status = "Online" if success else "Offline / Unreachable"

        embed = discord.Embed(
            title=f"Ping: {display_name}",
            color=color,
        )
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="IP", value=f"`{ip}`", inline=True)
        if summary:
            embed.add_field(name="Result", value=f"`{summary}`", inline=False)

        await interaction.followup.send(embed=embed)

    @ping.autocomplete("host")
    async def _ping_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        hosts = await get_all_hosts()
        return [
            app_commands.Choice(name=h["name"], value=h["name"])
            for h in hosts
            if current.lower() in h["name"].lower()
        ][:25]

    # ------------------------------------------------------------------
    # /wakeup
    # ------------------------------------------------------------------

    @app_commands.command(
        name="wakeup",
        description="Send a Wake-on-LAN magic packet to a host",
    )
    @is_management()
    @app_commands.describe(host="Host name (must have a MAC address in the DB)")
    async def wakeup(
        self,
        interaction: discord.Interaction,
        host: str,
    ):
        await interaction.response.defer(ephemeral=True)

        host_record = await get_host(host)
        if not host_record:
            await interaction.followup.send(
                f"No host named **{host}** found.", ephemeral=True
            )
            return

        mac = host_record.get("mac")
        if not mac:
            await interaction.followup.send(
                f"Host **{host}** has no MAC address configured. "
                "Use `/host add` or update the record first.",
                ephemeral=True,
            )
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_magic_packet, mac)
            logger.info(
                "%s sent WoL magic packet to %s (%s)", interaction.user, host, mac
            )
            await interaction.followup.send(
                f"Wake-on-LAN packet sent to **{host}** (`{mac}`).\n"
                "The host should boot within 30–60 seconds.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("WoL failed for %s: %s", host, exc)
            await interaction.followup.send(
                f"Failed to send WoL packet: {exc}", ephemeral=True
            )

    @wakeup.autocomplete("host")
    async def _wakeup_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        hosts = await get_all_hosts()
        # Only suggest hosts that have a MAC address registered
        return [
            app_commands.Choice(name=h["name"], value=h["name"])
            for h in hosts
            if h.get("mac") and current.lower() in h["name"].lower()
        ][:25]

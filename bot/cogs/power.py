import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.db import get_host, get_hosts_by_role
from bot.permissions import is_management

logger = logging.getLogger(__name__)

# Tasmota HTTP API command mapping
POWER_ACTIONS: dict[str, str] = {
    "on": "Power On",
    "off": "Power Off",
    "reboot": "Restart 1",
}

POWER_CHOICES = [
    app_commands.Choice(name="Power On", value="on"),
    app_commands.Choice(name="Power Off", value="off"),
    app_commands.Choice(name="Reboot", value="reboot"),
]


class PowerCog(commands.Cog, name="Power"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    # ------------------------------------------------------------------
    # /power  (send power commands to a host with the "Plug" role)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="power",
        description="Send a power command to a Tasmota smart plug (hosts with 'Plug' role)",
    )
    @is_management()
    @app_commands.describe(
        device="Host name (must have the 'Plug' role)",
        action="Power action to send",
    )
    @app_commands.choices(action=POWER_CHOICES)
    async def power(
        self,
        interaction: discord.Interaction,
        device: str,
        action: app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)

        host = await get_host(device)
        if not host:
            await interaction.followup.send(
                f"No host named **{device}** found.",
                ephemeral=True,
            )
            return

        # Check the host has the Plug role
        roles = [r.strip().lower() for r in (host["roles"] or "").split(",") if r.strip()]
        if "plug" not in roles:
            await interaction.followup.send(
                f"Host **{device}** doesn't have the **Plug** role. "
                "Add the role with `/host add` or update it first.",
                ephemeral=True,
            )
            return

        action_value = action.value
        tasmota_cmd = POWER_ACTIONS[action_value]
        encoded_cmd = tasmota_cmd.replace(" ", "%20")
        url = f"http://{host['ip']}/cm?cmnd={encoded_cmd}"

        logger.info(
            "%s sending power '%s' to %s (%s)",
            interaction.user,
            action_value,
            device,
            host["ip"],
        )

        try:
            session = self._get_session()
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(url, timeout=timeout) as resp:
                body = await resp.text()
                if resp.status == 200:
                    action_label = tasmota_cmd.title()
                    await interaction.followup.send(
                        f"**{action_label}** sent to **{device}**.\n"
                        f"Response: `{body[:300]}`",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"Plug responded with HTTP {resp.status}: `{body[:200]}`",
                        ephemeral=True,
                    )
        except aiohttp.ClientConnectorError:
            await interaction.followup.send(
                f"Could not reach **{device}** at `{host['ip']}`. Is it online?",
                ephemeral=True,
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                f"Request to **{device}** timed out.", ephemeral=True
            )
        except Exception as exc:
            logger.error("Power command failed for %s: %s", device, exc, exc_info=True)
            await interaction.followup.send(
                f"Command failed: {exc}", ephemeral=True
            )

    @power.autocomplete("device")
    async def _power_device_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        plugs = await get_hosts_by_role("Plug")
        return [
            app_commands.Choice(name=p["name"], value=p["name"])
            for p in plugs
            if current.lower() in p["name"].lower()
        ][:25]

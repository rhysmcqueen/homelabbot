import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.db import add_plug, get_all_plugs, get_plug, remove_plug
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
    # /plug  (manage smart plug registry)
    # ------------------------------------------------------------------

    plug = app_commands.Group(name="plug", description="Manage registered smart plugs")

    @plug.command(name="add", description="Register a new Tasmota smart plug")
    @is_management()
    @app_commands.describe(
        name="Friendly name for the plug",
        ip="IP address of the Tasmota device",
    )
    async def plug_add(
        self,
        interaction: discord.Interaction,
        name: str,
        ip: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            await add_plug(name, ip)
            await interaction.followup.send(
                f"Smart plug **{name}** (`{ip}`) registered.", ephemeral=True
            )
            logger.info("%s registered plug %s (%s)", interaction.user, name, ip)
        except Exception as exc:
            await interaction.followup.send(
                f"Failed to register plug: {exc}", ephemeral=True
            )

    @plug.command(name="remove", description="Remove a registered smart plug")
    @is_management()
    @app_commands.describe(name="Plug to remove")
    async def plug_remove(
        self,
        interaction: discord.Interaction,
        name: str,
    ):
        await interaction.response.defer(ephemeral=True)
        removed = await remove_plug(name)
        if removed:
            await interaction.followup.send(
                f"Plug **{name}** removed.", ephemeral=True
            )
            logger.info("%s removed plug %s", interaction.user, name)
        else:
            await interaction.followup.send(
                f"No plug named **{name}** found.", ephemeral=True
            )

    @plug_remove.autocomplete("name")
    async def _plug_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        plugs = await get_all_plugs()
        return [
            app_commands.Choice(name=p["name"], value=p["name"])
            for p in plugs
            if current.lower() in p["name"].lower()
        ][:25]

    @plug.command(name="list", description="List all registered smart plugs")
    async def plug_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        plugs = await get_all_plugs()
        if not plugs:
            await interaction.followup.send(
                "No smart plugs registered. Use `/plug add` to register one."
            )
            return
        embed = discord.Embed(title="Smart Plugs", color=discord.Color.orange())
        for p in plugs:
            embed.add_field(name=p["name"], value=f"`{p['ip']}`", inline=True)
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /power  (send power commands to a plug)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="power",
        description="Send a power command to a registered smart plug",
    )
    @is_management()
    @app_commands.describe(
        device="Smart plug name",
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

        plug = await get_plug(device)
        if not plug:
            await interaction.followup.send(
                f"No plug named **{device}** found. Register it with `/plug add`.",
                ephemeral=True,
            )
            return

        action_value = action.value
        tasmota_cmd = POWER_ACTIONS[action_value]
        encoded_cmd = tasmota_cmd.replace(" ", "%20")
        url = f"http://{plug['ip']}/cm?cmnd={encoded_cmd}"

        logger.info(
            "%s sending power '%s' to %s (%s)",
            interaction.user,
            action_value,
            device,
            plug["ip"],
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
                f"Could not reach **{device}** at `{plug['ip']}`. Is it online?",
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
        plugs = await get_all_plugs()
        return [
            app_commands.Choice(name=p["name"], value=p["name"])
            for p in plugs
            if current.lower() in p["name"].lower()
        ][:25]

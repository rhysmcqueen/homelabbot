import io
import json
import logging
from typing import Optional

import nextcord
from nextcord.ext import commands

from bot.config import GUILD_ID
from bot.db import (
    add_host,
    export_hosts_as_dict,
    get_all_hosts,
    get_host,
    import_hosts_from_dict,
    remove_host,
)
from bot.permissions import is_management, is_owner

logger = logging.getLogger(__name__)

HOSTS_PER_PAGE = 9  # 3-column grid looks clean


def _roles_list(host: dict) -> list[str]:
    return [r for r in host["roles"].split(",") if r] if host["roles"] else []


class HostListView(nextcord.ui.View):
    def __init__(self, hosts: list[dict], requester_id: int):
        super().__init__(timeout=120)
        self.hosts = hosts
        self.page = 0
        self.total_pages = max(1, (len(hosts) - 1) // HOSTS_PER_PAGE + 1)
        self.requester_id = requester_id
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    def build_embed(self) -> nextcord.Embed:
        start = self.page * HOSTS_PER_PAGE
        end = start + HOSTS_PER_PAGE
        page_hosts = self.hosts[start:end]

        embed = nextcord.Embed(
            title="Homelab Hosts",
            color=nextcord.Color.blue(),
            description=(
                f"Showing **{start + 1}–{min(end, len(self.hosts))}** "
                f"of **{len(self.hosts)}** hosts"
            ),
        )
        for h in page_hosts:
            roles = _roles_list(h)
            lines = [f"IP: `{h['ip']}`"]
            if h["mac"]:
                lines.append(f"MAC: `{h['mac']}`")
            if h["fqdn"]:
                lines.append(f"FQDN: `{h['fqdn']}`")
            if roles:
                lines.append(f"Roles: {', '.join(roles)}")
            embed.add_field(name=h["name"], value="\n".join(lines), inline=True)

        embed.set_footer(text=f"Page {self.page + 1} / {self.total_pages}")
        return embed

    @nextcord.ui.button(label="◀ Prev", style=nextcord.ButtonStyle.secondary)
    async def prev_button(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who ran this command can navigate.", ephemeral=True
            )
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @nextcord.ui.button(label="Next ▶", style=nextcord.ButtonStyle.secondary)
    async def next_button(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who ran this command can navigate.", ephemeral=True
            )
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class HostsCog(commands.Cog, name="Hosts"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /host  (parent command — unused directly)
    # ------------------------------------------------------------------

    @nextcord.slash_command(
        name="host", description="Host management commands", guild_ids=[GUILD_ID]
    )
    async def host(self, interaction: nextcord.Interaction):
        pass

    # ------------------------------------------------------------------
    # /host add
    # ------------------------------------------------------------------

    @host.subcommand(name="add", description="Add a new host to the database")
    @is_management()
    async def host_add(
        self,
        interaction: nextcord.Interaction,
        name: str = nextcord.SlashOption(description="Unique hostname identifier"),
        ip: str = nextcord.SlashOption(description="IPv4 address"),
        mac: Optional[str] = nextcord.SlashOption(
            description="MAC address for Wake-on-LAN (e.g. AA:BB:CC:DD:EE:FF)",
            required=False,
        ),
        fqdn: Optional[str] = nextcord.SlashOption(
            description="Fully qualified domain name", required=False
        ),
        roles: Optional[str] = nextcord.SlashOption(
            description="Comma-separated roles (e.g. vm,storage,hypervisor)",
            required=False,
        ),
    ):
        await interaction.response.defer(ephemeral=True)
        role_list = [r.strip() for r in roles.split(",")] if roles else []
        try:
            await add_host(name, ip, mac, fqdn, role_list)
            await interaction.followup.send(
                f"Host **{name}** (`{ip}`) added successfully.", ephemeral=True
            )
            logger.info("%s added host %s (%s)", interaction.user, name, ip)
        except Exception as exc:
            logger.error("Failed to add host %s: %s", name, exc)
            await interaction.followup.send(f"Failed to add host: {exc}", ephemeral=True)

    # ------------------------------------------------------------------
    # /host remove
    # ------------------------------------------------------------------

    @host.subcommand(name="remove", description="Remove a host from the database")
    @is_management()
    async def host_remove(
        self,
        interaction: nextcord.Interaction,
        name: str = nextcord.SlashOption(
            description="Host to remove", autocomplete=True
        ),
    ):
        await interaction.response.defer(ephemeral=True)
        removed = await remove_host(name)
        if removed:
            await interaction.followup.send(
                f"Host **{name}** removed.", ephemeral=True
            )
            logger.info("%s removed host %s", interaction.user, name)
        else:
            await interaction.followup.send(
                f"No host named **{name}** found.", ephemeral=True
            )

    @host_remove.on_autocomplete("name")
    async def _autocomplete_remove(
        self, interaction: nextcord.Interaction, name: str
    ):
        hosts = await get_all_hosts()
        choices = [h["name"] for h in hosts if name.lower() in h["name"].lower()]
        await interaction.response.send_autocomplete(choices[:25])

    # ------------------------------------------------------------------
    # /host info
    # ------------------------------------------------------------------

    @host.subcommand(name="info", description="Show details for a specific host")
    async def host_info(
        self,
        interaction: nextcord.Interaction,
        name: str = nextcord.SlashOption(
            description="Host name", autocomplete=True
        ),
    ):
        await interaction.response.defer()
        host = await get_host(name)
        if not host:
            await interaction.followup.send(f"No host named **{name}** found.")
            return

        roles = _roles_list(host)
        embed = nextcord.Embed(title=host["name"], color=nextcord.Color.blue())
        embed.add_field(name="IP Address", value=f"`{host['ip']}`", inline=True)
        embed.add_field(
            name="MAC Address", value=f"`{host['mac']}`" if host["mac"] else "—", inline=True
        )
        embed.add_field(
            name="FQDN", value=f"`{host['fqdn']}`" if host["fqdn"] else "—", inline=True
        )
        embed.add_field(
            name="Roles", value=", ".join(roles) if roles else "—", inline=False
        )
        embed.set_footer(text=f"Added: {host['created_at'][:10]}")
        await interaction.followup.send(embed=embed)

    @host_info.on_autocomplete("name")
    async def _autocomplete_info(
        self, interaction: nextcord.Interaction, name: str
    ):
        hosts = await get_all_hosts()
        choices = [h["name"] for h in hosts if name.lower() in h["name"].lower()]
        await interaction.response.send_autocomplete(choices[:25])

    # ------------------------------------------------------------------
    # /host list
    # ------------------------------------------------------------------

    @host.subcommand(name="list", description="List all hosts")
    async def host_list(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        hosts = await get_all_hosts()
        if not hosts:
            await interaction.followup.send(
                "No hosts in the database yet. Use `/host add` to get started."
            )
            return
        view = HostListView(hosts, interaction.user.id)
        await interaction.followup.send(embed=view.build_embed(), view=view)

    # ------------------------------------------------------------------
    # /host export
    # ------------------------------------------------------------------

    @host.subcommand(name="export", description="Export all hosts as a JSON file")
    @is_management()
    async def host_export(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = await export_hosts_as_dict()
        json_bytes = json.dumps(data, indent=2).encode("utf-8")
        file = nextcord.File(io.BytesIO(json_bytes), filename="hosts_export.json")
        await interaction.followup.send(
            f"Exported **{len(data)}** host(s).", file=file, ephemeral=True
        )
        logger.info("%s exported %d hosts", interaction.user, len(data))

    # ------------------------------------------------------------------
    # /host import
    # ------------------------------------------------------------------

    @host.subcommand(
        name="import",
        description="Import hosts from a JSON file — owner only",
    )
    @is_owner()
    async def host_import(
        self,
        interaction: nextcord.Interaction,
        file: nextcord.Attachment = nextcord.SlashOption(
            description="JSON file to import (hosts.json format)"
        ),
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            content = await file.read()
            data = json.loads(content)
            if not isinstance(data, dict):
                await interaction.followup.send(
                    "Invalid format: expected a JSON object.", ephemeral=True
                )
                return
            imported, skipped = await import_hosts_from_dict(data)
            await interaction.followup.send(
                f"Import complete: **{imported}** host(s) added, **{skipped}** skipped.",
                ephemeral=True,
            )
            logger.info(
                "%s imported hosts: %d added, %d skipped",
                interaction.user,
                imported,
                skipped,
            )
        except json.JSONDecodeError as exc:
            await interaction.followup.send(f"Invalid JSON: {exc}", ephemeral=True)
        except Exception as exc:
            logger.error("Host import failed: %s", exc, exc_info=True)
            await interaction.followup.send(f"Import failed: {exc}", ephemeral=True)

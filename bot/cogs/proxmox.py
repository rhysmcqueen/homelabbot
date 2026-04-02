import asyncio
import logging
import ssl
from typing import Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import PROXMOX_HOST, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET
from bot.permissions import is_management

logger = logging.getLogger(__name__)

VM_STATUS_EMOJI = {
    "running": "🟢",
    "stopped": "🔴",
    "paused": "🟡",
    "unknown": "⚪",
}

NODE_STATUS_EMOJI = {
    "online": "🟢",
    "offline": "🔴",
    "unknown": "⚪",
}


def _format_bytes(b: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _pct(val: float) -> str:
    return f"{val * 100:.1f}%"


class ProxmoxCog(commands.Cog, name="Proxmox"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"PVEAPIToken={PROXMOX_TOKEN_ID}={PROXMOX_TOKEN_SECRET}"
                },
                connector=aiohttp.TCPConnector(ssl=self._ssl_ctx),
            )
        return self._session

    def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def _api_get(self, path: str) -> Optional[dict]:
        """Make a GET request to the Proxmox API."""
        url = f"{PROXMOX_HOST}/api2/json{path}"
        try:
            session = self._get_session()
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error("Proxmox API %s returned %d", path, resp.status)
                return None
        except Exception as exc:
            logger.error("Proxmox API request failed: %s", exc)
            return None

    async def _get_resources(self, resource_type: Optional[str] = None) -> list[dict]:
        """Get cluster resources, optionally filtered by type."""
        path = "/cluster/resources"
        if resource_type:
            path += f"?type={resource_type}"
        data = await self._api_get(path)
        if data and "data" in data:
            return data["data"]
        return []

    # ------------------------------------------------------------------
    # /node list
    # ------------------------------------------------------------------

    node = app_commands.Group(name="node", description="Proxmox node commands")

    @node.command(name="list", description="Show all Proxmox cluster nodes and their status")
    async def node_list(self, interaction: discord.Interaction):
        await interaction.response.defer()

        nodes = await self._get_resources("node")
        if not nodes:
            await interaction.followup.send("Could not fetch node data from Proxmox.")
            return

        nodes.sort(key=lambda n: n.get("node", ""))

        embed = discord.Embed(
            title="Proxmox Cluster Nodes",
            color=discord.Color.blue(),
        )

        for n in nodes:
            status = n.get("status", "unknown")
            emoji = NODE_STATUS_EMOJI.get(status, "⚪")
            name = n.get("node", "?")

            if status == "online":
                cpu = _pct(n.get("cpu", 0))
                mem_used = _format_bytes(n.get("mem", 0))
                mem_total = _format_bytes(n.get("maxmem", 0))
                uptime_s = n.get("uptime", 0)
                days, rem = divmod(uptime_s, 86400)
                hours, rem = divmod(rem, 3600)
                mins, _ = divmod(rem, 60)
                uptime = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"

                value = (
                    f"CPU: `{cpu}`\n"
                    f"Memory: `{mem_used}` / `{mem_total}`\n"
                    f"Uptime: `{uptime}`"
                )
            else:
                value = f"Status: **{status}**"

            embed.add_field(
                name=f"{emoji} {name}",
                value=value,
                inline=True,
            )

        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /node status <node>
    # ------------------------------------------------------------------

    @node.command(name="status", description="Show detailed status for a specific node")
    @app_commands.describe(node_name="Proxmox node name (e.g. pve-3)")
    async def node_status(
        self,
        interaction: discord.Interaction,
        node_name: str,
    ):
        await interaction.response.defer()

        data = await self._api_get(f"/nodes/{node_name}/status")
        if not data or "data" not in data:
            await interaction.followup.send(
                f"Could not fetch status for node **{node_name}**. Is it online?"
            )
            return

        d = data["data"]
        cpu = _pct(d.get("cpu", 0))
        mem = d.get("memory", {})
        mem_used = _format_bytes(mem.get("used", 0))
        mem_total = _format_bytes(mem.get("total", 0))
        swap = d.get("swap", {})
        swap_used = _format_bytes(swap.get("used", 0))
        swap_total = _format_bytes(swap.get("total", 0))
        uptime_s = d.get("uptime", 0)
        days, rem = divmod(uptime_s, 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        uptime = f"{days}d {hours}h {mins}m"
        loadavg = d.get("loadavg", ["?", "?", "?"])
        cpuinfo = d.get("cpuinfo", {})
        cpu_model = cpuinfo.get("model", "?")
        cpu_cores = cpuinfo.get("cores", "?")
        cpu_sockets = cpuinfo.get("sockets", "?")

        embed = discord.Embed(
            title=f"Node: {node_name}",
            color=discord.Color.green(),
        )
        embed.add_field(name="CPU", value=f"`{cpu}` — {cpu_model}", inline=False)
        embed.add_field(
            name="Cores",
            value=f"{cpu_sockets} socket(s) × {cpu_cores} cores",
            inline=True,
        )
        embed.add_field(
            name="Load Average",
            value=f"`{' / '.join(str(l) for l in loadavg)}`",
            inline=True,
        )
        embed.add_field(name="Memory", value=f"`{mem_used}` / `{mem_total}`", inline=True)
        embed.add_field(name="Swap", value=f"`{swap_used}` / `{swap_total}`", inline=True)
        embed.add_field(name="Uptime", value=f"`{uptime}`", inline=True)

        # Kernel version
        kversion = d.get("kversion", "")
        if kversion:
            embed.add_field(name="Kernel", value=f"`{kversion}`", inline=False)

        await interaction.followup.send(embed=embed)

    @node_status.autocomplete("node_name")
    async def _node_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        nodes = await self._get_resources("node")
        return [
            app_commands.Choice(name=n["node"], value=n["node"])
            for n in nodes
            if current.lower() in n.get("node", "").lower()
        ][:25]

    # ------------------------------------------------------------------
    # /vm list
    # ------------------------------------------------------------------

    vm = app_commands.Group(name="vm", description="Proxmox VM commands")

    @vm.command(name="list", description="List all VMs across the cluster")
    async def vm_list(self, interaction: discord.Interaction):
        await interaction.response.defer()

        vms = await self._get_resources("vm")
        if not vms:
            await interaction.followup.send("No VMs found or could not reach Proxmox.")
            return

        # Sort: running first, then by name
        vms.sort(key=lambda v: (0 if v.get("status") == "running" else 1, v.get("name", "")))

        embed = discord.Embed(
            title="Proxmox VMs",
            color=discord.Color.blue(),
            description=f"**{len(vms)}** VMs total — "
            f"**{sum(1 for v in vms if v.get('status') == 'running')}** running",
        )

        # Limit to 25 fields (Discord embed limit)
        for v in vms[:25]:
            status = v.get("status", "unknown")
            emoji = VM_STATUS_EMOJI.get(status, "⚪")
            name = v.get("name", f"VM {v.get('vmid', '?')}")
            vmid = v.get("vmid", "?")
            node = v.get("node", "?")

            if status == "running":
                cpu = _pct(v.get("cpu", 0))
                mem_used = _format_bytes(v.get("mem", 0))
                mem_total = _format_bytes(v.get("maxmem", 0))
                value = (
                    f"ID: `{vmid}` • Node: `{node}`\n"
                    f"CPU: `{cpu}` • Mem: `{mem_used}`/`{mem_total}`"
                )
            else:
                value = f"ID: `{vmid}` • Node: `{node}`\n**{status}**"

            embed.add_field(name=f"{emoji} {name}", value=value, inline=True)

        if len(vms) > 25:
            embed.set_footer(text=f"Showing 25 of {len(vms)} VMs")

        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /vm status <name>
    # ------------------------------------------------------------------

    @vm.command(name="status", description="Show detailed status for a specific VM")
    @app_commands.describe(name="VM name or ID")
    async def vm_status(
        self,
        interaction: discord.Interaction,
        name: str,
    ):
        await interaction.response.defer()

        # Find the VM in cluster resources
        vms = await self._get_resources("vm")
        vm = None
        for v in vms:
            if (
                str(v.get("vmid")) == name
                or v.get("name", "").lower() == name.lower()
            ):
                vm = v
                break

        if not vm:
            await interaction.followup.send(f"No VM matching **{name}** found.")
            return

        vmid = vm["vmid"]
        node = vm["node"]
        vm_type = vm.get("type", "qemu")  # qemu or lxc
        status = vm.get("status", "unknown")
        emoji = VM_STATUS_EMOJI.get(status, "⚪")

        embed = discord.Embed(
            title=f"{emoji} {vm.get('name', f'VM {vmid}')}",
            color=discord.Color.green() if status == "running" else discord.Color.red(),
        )
        embed.add_field(name="VMID", value=f"`{vmid}`", inline=True)
        embed.add_field(name="Node", value=f"`{node}`", inline=True)
        embed.add_field(name="Type", value=vm_type.upper(), inline=True)
        embed.add_field(name="Status", value=f"**{status}**", inline=True)

        if status == "running":
            cpu = _pct(vm.get("cpu", 0))
            maxcpu = vm.get("maxcpu", "?")
            mem_used = _format_bytes(vm.get("mem", 0))
            mem_total = _format_bytes(vm.get("maxmem", 0))
            disk_used = _format_bytes(vm.get("disk", 0))
            disk_total = _format_bytes(vm.get("maxdisk", 0))
            uptime_s = vm.get("uptime", 0)
            days, rem = divmod(uptime_s, 86400)
            hours, rem = divmod(rem, 3600)
            mins, _ = divmod(rem, 60)
            uptime = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"

            embed.add_field(name="CPU", value=f"`{cpu}` ({maxcpu} cores)", inline=True)
            embed.add_field(name="Memory", value=f"`{mem_used}` / `{mem_total}`", inline=True)
            embed.add_field(name="Disk", value=f"`{disk_used}` / `{disk_total}`", inline=True)
            embed.add_field(name="Uptime", value=f"`{uptime}`", inline=True)

            # Network I/O
            netin = vm.get("netin", 0)
            netout = vm.get("netout", 0)
            if netin or netout:
                embed.add_field(
                    name="Network I/O",
                    value=f"↓ `{_format_bytes(netin)}` ↑ `{_format_bytes(netout)}`",
                    inline=True,
                )

        await interaction.followup.send(embed=embed)

    @vm_status.autocomplete("name")
    async def _vm_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        vms = await self._get_resources("vm")
        choices = []
        for v in vms:
            vm_name = v.get("name", f"VM {v.get('vmid', '?')}")
            if current.lower() in vm_name.lower() or current in str(v.get("vmid", "")):
                choices.append(
                    app_commands.Choice(name=vm_name, value=vm_name)
                )
        return choices[:25]

    # ------------------------------------------------------------------
    # /cluster  (quick cluster overview)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="cluster",
        description="Show a quick overview of the Proxmox cluster",
    )
    async def cluster_overview(self, interaction: discord.Interaction):
        await interaction.response.defer()

        resources = await self._get_resources()
        if not resources:
            await interaction.followup.send("Could not reach Proxmox API.")
            return

        nodes = [r for r in resources if r["type"] == "node"]
        vms = [r for r in resources if r["type"] in ("qemu", "lxc")]
        storage = [r for r in resources if r["type"] == "storage"]

        online_nodes = sum(1 for n in nodes if n.get("status") == "online")
        running_vms = sum(1 for v in vms if v.get("status") == "running")

        # Aggregate resources from online nodes
        total_cpu = sum(n.get("cpu", 0) for n in nodes if n.get("status") == "online")
        total_mem = sum(n.get("mem", 0) for n in nodes if n.get("status") == "online")
        total_maxmem = sum(n.get("maxmem", 0) for n in nodes if n.get("status") == "online")

        avg_cpu = total_cpu / max(online_nodes, 1)

        embed = discord.Embed(
            title="Proxmox Cluster Overview",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Nodes",
            value=f"**{online_nodes}** / {len(nodes)} online",
            inline=True,
        )
        embed.add_field(
            name="VMs",
            value=f"**{running_vms}** / {len(vms)} running",
            inline=True,
        )
        embed.add_field(
            name="Storage Pools",
            value=f"{sum(1 for s in storage if s.get('status') == 'available')} available",
            inline=True,
        )
        if online_nodes:
            embed.add_field(
                name="Cluster CPU",
                value=f"`{_pct(avg_cpu)}`",
                inline=True,
            )
            embed.add_field(
                name="Cluster Memory",
                value=f"`{_format_bytes(total_mem)}` / `{_format_bytes(total_maxmem)}`",
                inline=True,
            )

        # List online nodes
        node_lines = []
        for n in sorted(nodes, key=lambda x: x.get("node", "")):
            status = n.get("status", "unknown")
            emoji = NODE_STATUS_EMOJI.get(status, "⚪")
            node_lines.append(f"{emoji} **{n.get('node', '?')}** — {status}")
        embed.add_field(
            name="Node Status",
            value="\n".join(node_lines),
            inline=False,
        )

        await interaction.followup.send(embed=embed)

# HomelabBot

A Discord bot for managing your homelab infrastructure — host inventory, Wake-on-LAN, smart plug control, and network diagnostics, all from Discord slash commands.

## Features

- **Host inventory** — add, remove, list, and search hosts with IP, MAC, FQDN, and role tags
- **Import / Export** — migrate from the old `hosts.json` format or back up to JSON at any time
- **Network diagnostics** — ping any registered host or raw IP from Discord
- **Wake-on-LAN** — send magic packets to wake hosts remotely
- **Smart plug control** — power on/off/reboot Tasmota-compatible smart plugs via HTTP
- **Timers** — set countdown timers up to 60 minutes with optional labels
- **Role-based access control** — owner, management role, and everyone tiers
- **Structured logging** — console + rotating log file with configurable level
- **SQLite storage** — persistent, file-based database with no external dependencies
- **Docker-ready** — single container, mounts a `data/` volume for the DB and logs

## Quick Start (Docker)

```bash
# 1. Pull the image
docker pull ghcr.io/rhysmcqueen/homelabbot:latest

# 2. Create your env file
cp .env.example .env
# Edit .env and fill in BOT_TOKEN and GUILD_ID

# 3. Start
docker compose up -d
```

Logs and the database are written to `./data/` on the host.

## Manual Setup

```bash
# Clone
git clone https://github.com/rhysmcqueen/homelabbot.git
cd homelabbot

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env

# Run
python -m bot
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Discord bot token from the Developer Portal |
| `GUILD_ID` | Yes | — | ID of your Discord server |
| `OWNER_ID` | No | `478640098691514389` | Discord user ID with owner-level permissions |
| `MANAGEMENT_ROLE_ID` | No | `1127726166137126993` | Discord role ID for management-level permissions |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DATABASE_PATH` | No | `data/homelabbot.db` | Path to the SQLite database file |

## Command Reference

### Everyone

| Command | Description |
|---|---|
| `/hello` | Health check — confirms the bot is running |
| `/botinfo` | Shows bot version, uptime, host count, and guild info |
| `/ping <host>` | Ping a registered host or raw IP address |
| `/host list` | List all hosts (paginated) |
| `/host info <name>` | Show details for a specific host |
| `/plug list` | List all registered smart plugs |
| `/timer <minutes> [label]` | Set a countdown timer (1–60 minutes) |

### Management role or owner

| Command | Description |
|---|---|
| `/host add <name> <ip> [mac] [fqdn] [roles]` | Add a host to the database |
| `/host remove <name>` | Remove a host |
| `/host export` | Download all hosts as `hosts_export.json` |
| `/wakeup <host>` | Send a Wake-on-LAN magic packet |
| `/plug add <name> <ip>` | Register a Tasmota smart plug |
| `/plug remove <name>` | Remove a smart plug |
| `/power <device> <action>` | Send Power On / Power Off / Reboot to a plug |

### Owner only

| Command | Description |
|---|---|
| `/host import <file>` | Import hosts from an uploaded JSON file |
| `/setting` | View current bot configuration |

## Smart Plug Notes

Power commands use the [Tasmota](https://tasmota.github.io/) HTTP API:

```
GET http://<plug-ip>/cm?cmnd=Power%20On
GET http://<plug-ip>/cm?cmnd=Power%20Off
GET http://<plug-ip>/cm?cmnd=Restart%201
```

Register a plug with `/plug add`, then control it with `/power`.

## Migrating from the Old `hosts.json`

Use `/host import` and attach your existing `hosts.json` file. The bot will import compatible entries and report how many were added or skipped (duplicates/invalid entries).

## Architecture

```
bot/
├── __main__.py        Entry point — creates bot, loads cogs, starts event loop
├── config.py          All configuration from environment variables
├── db.py              Async SQLite layer (aiosqlite)
├── logging_config.py  Rotating file + console logging setup
├── permissions.py     is_owner() and is_management() check decorators
└── cogs/
    ├── admin.py       /botinfo, /setting
    ├── hosts.py       /host add|remove|info|list|export|import
    ├── network.py     /ping, /wakeup
    ├── power.py       /plug add|remove|list, /power
    └── tools.py       /hello, /timer
```

Runtime data (SQLite DB + log file) is written to `data/`, which is mounted as a Docker volume so it persists across container restarts.

## Contributing

Pull requests are welcome. Please open an issue first to discuss larger changes.

```bash
# Run locally with debug logging
LOG_LEVEL=DEBUG python -m bot
```

## License

MIT

import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return value


BOT_TOKEN: str = _require("BOT_TOKEN")
GUILD_ID: int = int(_require("GUILD_ID"))
OWNER_ID: int = int(os.getenv("OWNER_ID", "478640098691514389"))
MANAGEMENT_ROLE_ID: int = int(os.getenv("MANAGEMENT_ROLE_ID", "1127726166137126993"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/homelabbot.db")

# Proxmox API (optional — enables /node and /vm commands)
PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "")
PROXMOX_TOKEN_ID: str = os.getenv("PROXMOX_TOKEN_ID", "")
PROXMOX_TOKEN_SECRET: str = os.getenv("PROXMOX_TOKEN_SECRET", "")

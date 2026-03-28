import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from bot.config import DATABASE_PATH

logger = logging.getLogger(__name__)


def _ensure_data_dir() -> None:
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


async def init_db() -> None:
    _ensure_data_dir()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hosts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL COLLATE NOCASE,
                ip          TEXT NOT NULL,
                mac         TEXT,
                fqdn        TEXT,
                roles       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS smart_plugs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL COLLATE NOCASE,
                ip          TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("Database initialized at %s", DATABASE_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------

async def add_host(
    name: str,
    ip: str,
    mac: Optional[str] = None,
    fqdn: Optional[str] = None,
    roles: Optional[list[str]] = None,
) -> None:
    now = _now()
    roles_str = ",".join(r.strip() for r in roles) if roles else ""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO hosts (name, ip, mac, fqdn, roles, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, ip, mac or None, fqdn or None, roles_str, now, now),
        )
        await db.commit()
    logger.info("Added host: %s (%s)", name, ip)


async def remove_host(name: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM hosts WHERE name = ? COLLATE NOCASE", (name,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Removed host: %s", name)
    return deleted


async def get_host(name: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM hosts WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_all_hosts() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM hosts ORDER BY name COLLATE NOCASE")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_host(
    name: str,
    ip: Optional[str] = None,
    mac: Optional[str] = None,
    fqdn: Optional[str] = None,
    roles: Optional[list[str]] = None,
) -> bool:
    host = await get_host(name)
    if not host:
        return False
    new_ip = ip if ip is not None else host["ip"]
    new_mac = mac if mac is not None else host["mac"]
    new_fqdn = fqdn if fqdn is not None else host["fqdn"]
    new_roles = ",".join(roles) if roles is not None else host["roles"]
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """UPDATE hosts SET ip=?, mac=?, fqdn=?, roles=?, updated_at=?
               WHERE name=? COLLATE NOCASE""",
            (new_ip, new_mac, new_fqdn, new_roles, _now(), name),
        )
        await db.commit()
    return True


async def get_host_count() -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM hosts")
        row = await cursor.fetchone()
    return row[0] if row else 0


async def import_hosts_from_dict(data: dict) -> tuple[int, int]:
    """Import hosts from a dict in the legacy hosts.json format.

    Returns (imported_count, skipped_count).
    """
    imported = skipped = 0
    for key, host in data.items():
        name = host.get("host_name") or key
        ip = host.get("ip", "")
        mac = host.get("mac") or None
        fqdn = host.get("FQDN") or None
        roles = host.get("role", [])
        try:
            await add_host(name, ip, mac, fqdn, roles)
            imported += 1
        except Exception as exc:
            logger.warning("Skipped host %s during import: %s", name, exc)
            skipped += 1
    return imported, skipped


async def export_hosts_as_dict() -> dict:
    hosts = await get_all_hosts()
    result: dict = {}
    for h in hosts:
        roles = [r for r in h["roles"].split(",") if r] if h["roles"] else []
        result[h["name"]] = {
            "host_name": h["name"],
            "ip": h["ip"],
            "mac": h["mac"],
            "FQDN": h["fqdn"],
            "role": roles,
        }
    return result


# ---------------------------------------------------------------------------
# Smart Plugs
# ---------------------------------------------------------------------------

async def add_plug(name: str, ip: str) -> None:
    now = _now()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO smart_plugs (name, ip, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, ip, now, now),
        )
        await db.commit()
    logger.info("Added smart plug: %s (%s)", name, ip)


async def remove_plug(name: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM smart_plugs WHERE name = ? COLLATE NOCASE", (name,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_plug(name: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM smart_plugs WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_all_plugs() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM smart_plugs ORDER BY name COLLATE NOCASE"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]

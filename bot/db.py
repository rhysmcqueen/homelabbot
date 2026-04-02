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

        # Migrate: import any existing smart_plugs into hosts, then drop the table
        try:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='smart_plugs'"
            )
            if await cursor.fetchone():
                plug_cursor = await db.execute("SELECT name, ip, created_at, updated_at FROM smart_plugs")
                plugs = await plug_cursor.fetchall()
                for plug_name, plug_ip, created, updated in plugs:
                    # Check if a host with this name already exists
                    existing = await db.execute(
                        "SELECT id FROM hosts WHERE name = ? COLLATE NOCASE", (plug_name,)
                    )
                    if not await existing.fetchone():
                        await db.execute(
                            """INSERT INTO hosts (name, ip, mac, fqdn, roles, created_at, updated_at)
                               VALUES (?, ?, NULL, NULL, 'Plug', ?, ?)""",
                            (plug_name, plug_ip, created, updated),
                        )
                        logger.info("Migrated smart plug '%s' to hosts with role 'Plug'", plug_name)
                    else:
                        # Host exists — just ensure it has the Plug role
                        row = await db.execute(
                            "SELECT roles FROM hosts WHERE name = ? COLLATE NOCASE", (plug_name,)
                        )
                        host_row = await row.fetchone()
                        if host_row:
                            existing_roles = host_row[0] or ""
                            if "Plug" not in existing_roles:
                                new_roles = f"{existing_roles},Plug" if existing_roles else "Plug"
                                await db.execute(
                                    "UPDATE hosts SET roles = ? WHERE name = ? COLLATE NOCASE",
                                    (new_roles, plug_name),
                                )
                        logger.info("Smart plug '%s' already exists as host, added Plug role", plug_name)
                await db.execute("DROP TABLE smart_plugs")
                logger.info("Migrated smart_plugs table into hosts and dropped it")
        except Exception as exc:
            logger.warning("Smart plug migration check failed (safe to ignore): %s", exc)

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


async def get_hosts_by_role(role: str) -> list[dict]:
    """Return all hosts that have a specific role."""
    all_hosts = await get_all_hosts()
    return [
        h for h in all_hosts
        if role.lower() in [r.strip().lower() for r in (h["roles"] or "").split(",") if r.strip()]
    ]


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

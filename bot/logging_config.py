import logging
import logging.handlers
import os


def setup_logging(log_level: str = "", database_path: str = "") -> None:
    # Lazy import to avoid circular dependency at module load time
    if not log_level or not database_path:
        from bot.config import LOG_LEVEL, DATABASE_PATH
        log_level = log_level or LOG_LEVEL
        database_path = database_path or DATABASE_PATH

    log_dir = os.path.dirname(database_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir or ".", "bot.log")

    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Reduce noise from third-party libraries
    for noisy in ("discord", "websockets", "aiohttp", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

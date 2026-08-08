"""Logging + disk hygiene for the bot.

Two responsibilities, both previously missing entirely:

1. setup_logging(): send everything the process emits -- the bot's own
   messages, discord.py, apscheduler tracebacks, and bare print() calls -- to a
   time-rotating log file that keeps only the last ~30 minutes, while still
   echoing to the real stdout so `docker logs discordbot` keeps working.

2. cleanup_old_files(): delete generated images and stale log files older than
   30 minutes. The bot writes image files (SPOILER_*.png, <id>.png, ...) into
   its working directory for every NSFW/preview check and never removed them;
   9 such files had accumulated. This reaps them so the container's writable
   layer does not grow without bound.

Tunable via env vars (with production-sane defaults):
    LOG_DIR              default /app/logs
    IMAGE_DIR            default the current working directory (/app)
    FILE_MAX_AGE_MIN     default 30   (minutes; images + logs older than this go)
    LOG_ROTATE_MIN      default 10   (rotate the active log every N minutes)
"""

import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "/app/logs"))
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", os.getcwd()))
MAX_AGE_SECONDS = int(os.getenv("FILE_MAX_AGE_MIN", "30")) * 60
LOG_ROTATE_MIN = int(os.getenv("LOG_ROTATE_MIN", "10"))
LOG_FILE = LOG_DIR / "bot.log"

# Runtime-generated media the bot scatters into its working dir. Everything the
# .gitignore treats as disposable output; none of it is a permanent asset.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".mov", ".mp4", ".webp"}

log = logging.getLogger("discordbot.maintenance")


class _StreamToLogger:
    """File-like shim so legacy print()/tracebacks land in the log file too."""

    def __init__(self, logger, level):
        self._logger = logger
        self._level = level
        self._buffer = ""

    def write(self, message):
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._logger.log(self._level, line)

    def flush(self):
        if self._buffer.strip():
            self._logger.log(self._level, self._buffer.strip())
        self._buffer = ""


def setup_logging():
    """Configure root logging. Call once, as early as possible in main()."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotate every LOG_ROTATE_MIN minutes; keep just enough backups to cover the
    # 30-minute window, so old logs are auto-deleted by the handler itself.
    backups = max(1, (MAX_AGE_SECONDS // 60) // LOG_ROTATE_MIN)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE, when="M", interval=LOG_ROTATE_MIN, backupCount=backups, utc=True
    )
    file_handler.setFormatter(fmt)

    # Console handler writes to the ORIGINAL stdout (captured before we redirect
    # print()), so echoing to the console can never recurse back into logging.
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [file_handler, console_handler]

    # Route bare print() and any library that writes to stdout/stderr (e.g.
    # apscheduler's uncaught tracebacks) into the same log stream.
    sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)

    logging.getLogger("discord").setLevel(logging.INFO)
    log.info(
        "Logging initialised: file=%s rotate=%dm keep=%d backups (~%dm retained)",
        LOG_FILE, LOG_ROTATE_MIN, backups, MAX_AGE_SECONDS // 60,
    )


def cleanup_old_files():
    """Delete generated images and stale logs older than FILE_MAX_AGE_MIN.

    Safe to call on a schedule. Never raises: a hygiene task must not be able to
    take the bot down.
    """
    cutoff = time.time() - MAX_AGE_SECONDS
    removed_images = removed_logs = 0

    try:
        for entry in IMAGE_DIR.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed_images += 1
            except OSError as e:
                log.warning("Could not remove image %s: %s", entry, e)
    except OSError as e:
        log.warning("Could not scan image dir %s: %s", IMAGE_DIR, e)

    # Reap any rotated log files the handler's backupCount missed (belt and
    # suspenders), but never the active bot.log.
    try:
        for entry in LOG_DIR.glob("bot.log.*"):
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed_logs += 1
            except OSError as e:
                log.warning("Could not remove log %s: %s", entry, e)
    except OSError as e:
        log.warning("Could not scan log dir %s: %s", LOG_DIR, e)

    if removed_images or removed_logs:
        log.info(
            "cleanup: removed %d image(s), %d log file(s) older than %d min",
            removed_images, removed_logs, MAX_AGE_SECONDS // 60,
        )
    return removed_images, removed_logs

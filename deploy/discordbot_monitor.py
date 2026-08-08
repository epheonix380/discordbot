#!/usr/bin/env python3
"""External health monitor + Discord alerter for the discord bot.

Runs on the HOST (not in the container) on a systemd timer, so it stays alive
when the bot container itself is down. It checks the things that actually mean
"the bot works" and, on a state change, posts to a Discord channel.

Why these specific checks
-------------------------
The 2026-07-23 outage was a bot that reported **healthy** while every database
query failed -- the gateway heartbeat (and therefore Docker's healthcheck) was
blind to it. So this monitor checks THREE independent signals:

  1. container is running        (docker inspect .State.Status)
  2. gateway heartbeat is fresh  (docker inspect .State.Health.Status == healthy)
  3. the database is reachable   (a real `SELECT 1` run inside the container,
                                  using the bot's own Django config/credentials)

Any of them failing for MONITOR_FAIL_THRESHOLD consecutive checks => DOWN alert.
When all three pass again after a DOWN => RECOVERED alert. Alerts fire only on
state CHANGES (a small state file), so a persistent outage does not spam.

Alerting
--------
Sends via the Discord REST API using the main bot token
(`Authorization: Bot <TOKEN>`). REST needs no gateway session, so it never
conflicts with the running bot and works even when the bot is wedged.

Config (from the environment; systemd loads /root/discordbot/.env, and when run
by hand this script also parses that file itself):

  TOKEN                 (required) the bot token, reused for REST sends
  ALERT_CHANNEL_ID      (required) numeric Discord channel id to post alerts to
  CONTAINER             default "discordbot"
  MONITOR_FAIL_THRESHOLD default 2   (consecutive bad checks before alerting)
  MONITOR_CHECK_DB      default "1"  (set "0" to skip the DB probe)
  MONITOR_STATE_FILE    default /run/discordbot-monitor.state

Usage:
  discordbot_monitor.py            run one check; alert on state change
  discordbot_monitor.py --check    print health, never alert (for debugging)
  discordbot_monitor.py --test     send a test message and exit
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ENV_FILE = os.getenv("MONITOR_ENV_FILE", "/root/discordbot/.env")
CONTAINER = os.getenv("CONTAINER", "discordbot")
STATE_FILE = os.getenv("MONITOR_STATE_FILE", "/run/discordbot-monitor.state")
FAIL_THRESHOLD = int(os.getenv("MONITOR_FAIL_THRESHOLD", "2"))
CHECK_DB = os.getenv("MONITOR_CHECK_DB", "1") == "1"


def load_env_file(path):
    """Minimal KEY=VALUE parser so this works when launched by hand, not just
    under systemd's EnvironmentFile. Never overrides an already-set env var."""
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
    except OSError:
        pass


def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _docker(*args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=60
    )


def check_health():
    """Return (ok: bool, reason: str). reason is human-readable for the alert."""
    # 1) container exists & running
    r = _docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    if r.returncode != 0:
        return False, "container does not exist (never created / pruned)"
    state = r.stdout.strip()
    if state != "running":
        return False, f"container is not running (state={state})"

    # 2) gateway heartbeat freshness, via the compose healthcheck
    r = _docker(
        "inspect",
        "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        CONTAINER,
    )
    health = r.stdout.strip()
    if health == "unhealthy":
        return False, "gateway heartbeat is stale (container unhealthy)"
    if health == "starting":
        # Inside start_period (booting). Not an outage; report OK so we don't
        # alert on every normal restart.
        return True, "starting (within start_period)"

    # 3) database reachable, using the bot's own Django config INSIDE the
    #    container -- this is the check that would have caught the 07-23 outage.
    if CHECK_DB:
        probe = (
            "import os,django;"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.settings');"
            "django.setup();"
            "from django.db import connection;"
            "connection.cursor().execute('SELECT 1')"
        )
        r = _docker("exec", CONTAINER, "python", "-c", probe)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()
            detail = tail[-1] if tail else "unknown error"
            return False, f"database unreachable ({detail})"

    return True, "healthy"


def send_discord(content):
    """Post a message via the Discord REST API using the bot token. Returns
    True on success. Never raises."""
    token = os.environ.get("TOKEN")
    channel = os.environ.get("ALERT_CHANNEL_ID")
    if not token or not channel:
        print("[monitor] TOKEN or ALERT_CHANNEL_ID not set - cannot send alert",
              file=sys.stderr)
        return False
    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    data = json.dumps({"content": content}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "discordbot-monitor/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        print(f"[monitor] Discord API {e.code}: {body}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - alerting must never crash the monitor
        print(f"[monitor] send failed: {e}", file=sys.stderr)
    return False


def load_state():
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"status": "up", "fail_count": 0, "reason": ""}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as fh:
            json.dump(state, fh)
    except OSError as e:
        print(f"[monitor] could not persist state: {e}", file=sys.stderr)


def main():
    load_env_file(ENV_FILE)

    if "--test" in sys.argv:
        ok = send_discord(f"\U0001f9ea discord-bot monitor test message ({now_str()})")
        print("test message sent" if ok else "test message FAILED")
        return 0 if ok else 1

    ok, reason = check_health()

    if "--check" in sys.argv:
        print(f"{'OK' if ok else 'DOWN'}: {reason}")
        return 0 if ok else 1

    state = load_state()
    prev = state.get("status", "up")

    if ok:
        if prev == "down":
            send_discord(f"\U0001f7e2 **Bot RECOVERED** — {reason} ({now_str()})")
            print(f"[monitor] recovered: {reason}")
        save_state({"status": "up", "fail_count": 0, "reason": reason})
        return 0

    # not ok
    fail_count = state.get("fail_count", 0) + 1
    if prev == "up" and fail_count >= FAIL_THRESHOLD:
        send_discord(
            f"\U0001f534 **Bot DOWN** — {reason} "
            f"(failed {fail_count} checks; {now_str()})"
        )
        print(f"[monitor] ALERT sent: {reason}")
        save_state({"status": "down", "fail_count": fail_count, "reason": reason})
    else:
        print(f"[monitor] unhealthy ({fail_count}/{FAIL_THRESHOLD}): {reason}")
        # stay in previous status until threshold reached
        save_state({"status": prev, "fail_count": fail_count, "reason": reason})
    return 1


if __name__ == "__main__":
    sys.exit(main())

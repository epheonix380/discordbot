#!/usr/bin/env bash
#
# Restarts the bot when its container is alive but its Discord gateway is not.
#
# Docker's "restart: always" only reacts to the process exiting. It does NOT
# react to a failing healthcheck -- an unhealthy container is left running
# forever. That gap is this script's entire reason to exist: main.py only
# refreshes its heartbeat while the gateway is genuinely healthy, the compose
# healthcheck fails when that heartbeat goes stale, and this turns the
# resulting "unhealthy" state into an actual restart.

set -euo pipefail

CONTAINER=discordbot
COMPOSE_DIR=/root/discordbot
MAINTENANCE_FLAG=/run/discordbot.maintenance

log() { echo "[discordbot-watchdog] $*"; }

# Deliberate downtime escape hatch. Without this the watchdog would fight an
# operator who stopped the bot on purpose, bringing it back within 2 minutes.
#   touch /run/discordbot.maintenance   (cleared automatically on reboot)
if [[ -e "$MAINTENANCE_FLAG" ]]; then
    log "maintenance flag present - standing down"
    exit 0
fi

bring_up() {
    cd "$COMPOSE_DIR"
    docker compose up -d --remove-orphans
}

# Container missing entirely (pruned, or never created after a failed deploy).
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    log "container '$CONTAINER' does not exist - recreating"
    bring_up
    exit 0
fi

state=$(docker inspect -f '{{.State.Status}}' "$CONTAINER")
health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER")

if [[ "$state" != "running" ]]; then
    # Do NOT assume "restart: always" covers this. Docker deliberately does not
    # apply restart policies to a container stopped by an explicit user command
    # (docker stop / docker kill) - it stays exited indefinitely. Verified on
    # this host: a SIGKILLed container sat in "exited" with RestartCount=0.
    # That is precisely the hole this watchdog exists to plug, so start it.
    log "state=$state (not running) - starting"
    bring_up
    exit 0
fi

case "$health" in
    healthy)
        exit 0
        ;;
    starting)
        # Inside start_period. Restarting here would loop forever on a slow boot.
        log "health=starting - still inside start_period, no action"
        exit 0
        ;;
    none)
        log "WARNING: no healthcheck defined on '$CONTAINER' - cannot verify liveness"
        exit 0
        ;;
    unhealthy)
        log "health=unhealthy - gateway heartbeat is stale, restarting"
        docker inspect -f '{{range .State.Health.Log}}{{.Output}}{{end}}' "$CONTAINER" 2>/dev/null | tail -3 || true
        cd "$COMPOSE_DIR"
        docker compose restart
        log "restart issued"
        ;;
    *)
        log "unexpected health='$health' - no action"
        ;;
esac

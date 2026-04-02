#!/bin/bash
# NightMend ECS Deploy Script
# Usage: bash deploy.sh <tarball.tar.gz>
# Called from local Mac via: scp + ssh or direct invocation
# Logs to /var/log/nightmend-deploy.log

set -euo pipefail

DEPLOY_DIR="/opt/nightmend"
LOG_FILE="/var/log/nightmend-deploy.log"
TARBALL="${1:-}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() {
    echo "[${TIMESTAMP}] $*" | tee -a "$LOG_FILE"
}

log "===== NightMend Deploy Started ====="

# ── Step 1: Receive and extract tarball ──────────────────────────────────────
if [[ -n "$TARBALL" && -f "$TARBALL" ]]; then
    log "Extracting tarball: $TARBALL"
    tar -xzf "$TARBALL" -C "$DEPLOY_DIR" --strip-components=1
    log "Extraction complete."
elif [[ -f "${DEPLOY_DIR}/incoming.tar.gz" ]]; then
    log "Extracting incoming.tar.gz"
    tar -xzf "${DEPLOY_DIR}/incoming.tar.gz" -C "$DEPLOY_DIR" --strip-components=1
    rm -f "${DEPLOY_DIR}/incoming.tar.gz"
    log "Extraction complete."
else
    log "No tarball provided or found at ${DEPLOY_DIR}/incoming.tar.gz"
    log "Proceeding with files already in place."
fi

# ── Step 2: Rebuild Docker Compose ───────────────────────────────────────────
cd "$DEPLOY_DIR"

log "Pulling latest base images..."
docker compose pull --quiet 2>&1 | tee -a "$LOG_FILE" || true

log "Building and restarting services..."
docker compose up -d --build --remove-orphans 2>&1 | tee -a "$LOG_FILE"

# ── Step 3: Health Check ─────────────────────────────────────────────────────
log "Waiting for services to become healthy (up to 60s)..."

BACKEND_PORT="${BACKEND_PORT:-8001}"
HEALTH_URL="http://localhost:${BACKEND_PORT}/health"
MAX_WAIT=60
WAITED=0

until curl -sf "$HEALTH_URL" > /dev/null 2>&1; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        log "ERROR: Health check failed after ${MAX_WAIT}s. Backend not responding on ${HEALTH_URL}"
        docker compose ps 2>&1 | tee -a "$LOG_FILE"
        exit 1
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    log "  ...waiting (${WAITED}s)"
done

log "Health check passed: ${HEALTH_URL}"

# ── Step 4: Verify container status ──────────────────────────────────────────
log "Container status:"
docker compose ps 2>&1 | tee -a "$LOG_FILE"

log "===== NightMend Deploy Finished at ${TIMESTAMP} ====="

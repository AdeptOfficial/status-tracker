#!/bin/bash
# Deploy status-tracker to dev server (LXC <media-dev>)
#
# Usage: ./scripts/deploy.sh
#
# Prerequisites:
#   - SSH access to Proxmox host (<dev-proxmox>)
#   - LXC <media-dev> running with Docker

set -e

PROXMOX_HOST="${PROXMOX_HOST:?set PROXMOX_HOST, e.g. root@<dev-proxmox> (values: homeserver configs/dev/services/<app>/README.md)}"
LXC_ID="${LXC_ID:?set LXC_ID of the dev container (see homeserver dev service README)}"
REMOTE_PATH="/opt/status-tracker"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Status Tracker Deploy ==="
echo "Source: $PROJECT_DIR"
echo "Target: LXC $LXC_ID at $REMOTE_PATH"
echo ""

# Step 1: Create tarball (excluding dev/build artifacts)
echo "[1/4] Creating tarball..."
TARBALL="/tmp/status-tracker-deploy.tar.gz"
cd "$PROJECT_DIR"
tar -czf "$TARBALL" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    --exclude='.env' \
    .

echo "[2/4] Copying to Proxmox host..."
scp "$TARBALL" "$PROXMOX_HOST:/tmp/"

echo "[3/4] Extracting in LXC..."
ssh "$PROXMOX_HOST" "pct push $LXC_ID /tmp/status-tracker-deploy.tar.gz /tmp/status-tracker-deploy.tar.gz"
ssh "$PROXMOX_HOST" "pct exec $LXC_ID -- bash -c 'cd $REMOTE_PATH && tar -xzf /tmp/status-tracker-deploy.tar.gz && rm /tmp/status-tracker-deploy.tar.gz'"

echo "[4/4] Rebuilding container..."
ssh "$PROXMOX_HOST" "pct exec $LXC_ID -- bash -c 'cd $REMOTE_PATH && docker compose up -d --build'"

# Cleanup local tarball
rm -f "$TARBALL"

echo ""
echo "=== Deploy Complete ==="
echo "Check logs: ssh $PROXMOX_HOST \"pct exec $LXC_ID -- docker logs status-tracker -f\""

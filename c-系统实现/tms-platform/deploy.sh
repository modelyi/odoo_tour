#!/bin/bash
# TMS Platform Deployment Script
# Odoo 19 + PostgreSQL + Redis

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=== TMS Deployment Started ==="
echo "Project: $PROJECT_DIR"
echo "Time: $(date)"
echo

# 1. Pull latest code if git repo exists
if [ -d ".git" ]; then
    echo "[1/6] Pulling latest code..."
    git pull --ff-only || echo "Warning: git pull failed, continuing..."
else
    echo "[1/6] Not a git repository, skipping git pull"
fi
echo

# 2. Stop Odoo container
echo "[2/6] Stopping Odoo container..."
docker stop tms-odoo 2>/dev/null || echo "Container not running"
docker rm tms-odoo 2>/dev/null || echo "Container not found"
echo

# 3. Rebuild/restart containers
echo "[3/6] Rebuilding and starting containers..."
docker compose up -d --build
echo

# 4. Wait for database to be ready
echo "[4/6] Waiting for database..."
sleep 10
docker exec tms-db pg_isready -U odoo
echo

# 5. Run module updates
echo "[5/6] Updating Odoo modules..."
docker exec tms-odoo odoo -d tms -u all --stop-after-init 2>&1 | tail -20
echo

# 6. Restart Odoo and verify
echo "[6/6] Restarting Odoo and verifying..."
docker restart tms-odoo
sleep 15

# Health check
if curl -fsS http://127.0.0.1:8070/web/database/list >/dev/null; then
    echo "✓ Health check passed"
else
    echo "✗ Health check failed"
    exit 1
fi

echo
echo "=== Deployment Complete ==="
echo "Access: https://tms.solepro.cloud"
echo "Admin password: $(grep ADMIN_PASSWD .env | cut -d= -f2)"
echo
docker ps --filter name=tms- --format "table {{.Names}}\t{{.Status}}"

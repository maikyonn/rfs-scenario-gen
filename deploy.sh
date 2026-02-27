#!/usr/bin/env bash
set -euo pipefail
cd /home/path/rfs-scenario-gen

echo "=== Deploy started at $(date) ==="

git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Already up to date."
    exit 0
fi

git pull origin main

# Reinstall Python deps if requirements changed
if git diff "$LOCAL" "$REMOTE" -- generator/requirements.txt | grep -q .; then
    echo "requirements.txt changed — reinstalling deps..."
    generator/.venv/bin/pip install -r generator/requirements.txt
fi

sudo systemctl restart rfs-api
echo "Deployed $(git rev-parse --short HEAD)"

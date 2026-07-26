#!/usr/bin/env bash
set -e
mkdir -p /data
export DEVIS_DB_PATH=/data/devis.db
cd /app
exec python3 app.py

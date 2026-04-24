#!/usr/bin/with-contenv bashio
export HA_TOKEN="${SUPERVISOR_TOKEN}"
export HA_URL="http://supervisor/core"
node /app/server.js

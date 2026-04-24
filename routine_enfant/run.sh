#!/usr/bin/env bashio
export HA_TOKEN=$(bashio::config 'ha_token')
export HA_URL=$(bashio::config 'ha_url')
node /app/server.js

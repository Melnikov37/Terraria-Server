#!/bin/bash
set -eo pipefail

TERRARIA_DIR="${TERRARIA_DIR:-/opt/terraria}"
FIFO="${TERRARIA_DIR}/.server-input"
PORT="${PORT:-7777}"
MAX_PLAYERS="${MAX_PLAYERS:-8}"
WORLD_NAME="${WORLD_NAME:-TerrariaWorld}"
DIFFICULTY="${DIFFICULTY:-0}"   # 0=Classic 1=Expert 2=Master 3=Journey
AUTOCREATE="${AUTOCREATE:-2}"   # 1=Small 2=Medium 3=Large

# Create persistent directories
mkdir -p "${TERRARIA_DIR}/worlds" \
         "${TERRARIA_DIR}/tModLoader/Mods" \
         "${TERRARIA_DIR}/backups"

# Persist the baked-in tModLoader version so the admin panel can read it
if [ -f /server/version.txt ]; then
    cp /server/version.txt "${TERRARIA_DIR}/.server_version"
fi

# Set up FIFO so the admin panel can write commands to server stdin
rm -f "$FIFO"
mkfifo "$FIFO"
# Open FIFO for writing from our side to keep it permanently open (prevents EOF on reader)
exec 3>"$FIFO"

# Build server arguments
ARGS=(-port "$PORT" -maxplayers "$MAX_PLAYERS")

WORLD_FILE="${TERRARIA_DIR}/worlds/${WORLD_NAME}.wld"
if [ -n "$WORLD" ] && [ -f "$WORLD" ]; then
    ARGS+=(-world "$WORLD")
elif [ -f "$WORLD_FILE" ]; then
    ARGS+=(-world "$WORLD_FILE")
else
    ARGS+=(-worldname "$WORLD_NAME" -autocreate "$AUTOCREATE" -difficulty "$DIFFICULTY")
fi

[ -n "$SERVER_PASSWORD" ] && ARGS+=(-pass "$SERVER_PASSWORD")

echo "[terraria-entrypoint] Args: ${ARGS[*]}"

# Detect how to run tModLoader
if [ -f /server/tModLoaderServer ] && [ -x /server/tModLoaderServer ]; then
    BIN=(/server/tModLoaderServer)
elif [ -f /server/start-tModLoaderServer.sh ]; then
    BIN=(bash /server/start-tModLoaderServer.sh)
else
    BIN=(dotnet /server/tModLoader.dll)
    ARGS=("-server" "${ARGS[@]}")
fi

# Run server with stdin fed from the FIFO.
# Anything written to $FIFO by the admin panel goes to server's stdin as a command.
tail -f "$FIFO" | "${BIN[@]}" "${ARGS[@]}"

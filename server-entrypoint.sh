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

# Build server arguments.
# -worldpath ensures worlds are always saved to the shared volume (/opt/terraria/worlds/)
# so the admin panel can list and switch them.
ARGS=(-port "$PORT" -maxplayers "$MAX_PLAYERS" -worldpath "${TERRARIA_DIR}/worlds")

SERVERCONFIG="${TERRARIA_DIR}/serverconfig.txt"
WORLD_FILE="${TERRARIA_DIR}/worlds/${WORLD_NAME}.wld"

if [ -f "$SERVERCONFIG" ]; then
    # Admin panel has written a serverconfig (via world switch / recreate).
    # Pass it to the server — it contains the world= path, difficulty, etc.
    ARGS+=(-config "$SERVERCONFIG")
elif [ -n "$WORLD" ] && [ -f "$WORLD" ]; then
    ARGS+=(-world "$WORLD")
elif [ -f "$WORLD_FILE" ]; then
    ARGS+=(-world "$WORLD_FILE")
else
    ARGS+=(-worldname "$WORLD_NAME" -autocreate "$AUTOCREATE" -difficulty "$DIFFICULTY")
fi

[ -n "$SERVER_PASSWORD" ] && ARGS+=(-pass "$SERVER_PASSWORD")

echo "[terraria-entrypoint] Args: ${ARGS[*]}"

# Detect how to run tModLoader.
# Prefer dotnet tModLoader.dll directly: bypasses start-tModLoaderServer.sh →
# ScriptCaller.sh which inserts an internal pipe (| tee Logs/server.log).
# That pipe causes .NET to switch to block-buffered stdout (4 KB chunks), making
# Docker logs empty until the buffer fills.  With tty:true + direct dotnet, .NET
# sees a PTY on stdout and uses line-buffered mode → logs appear immediately.
if [ -f /server/tModLoader.dll ]; then
    cd /server
    BIN=(dotnet /server/tModLoader.dll)
    ARGS=("-server" "${ARGS[@]}")
elif [ -f /server/tModLoaderServer ] && [ -x /server/tModLoaderServer ]; then
    BIN=(/server/tModLoaderServer)
else
    BIN=(bash /server/start-tModLoaderServer.sh)
fi

echo "[terraria-entrypoint] Binary: ${BIN[*]}"

# Run server with stdin fed from the FIFO.
# Process substitution (<(...)) feeds FIFO content as stdin without putting the
# server process inside a pipeline — its stdout stays directly on the container PTY.
# With tty:true, .NET detects isatty(stdout)=true → line-buffered → logs appear instantly.
exec "${BIN[@]}" "${ARGS[@]}" < <(tail -f "$FIFO")

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

# Launch order:
# 1. start-tModLoaderServer.sh  — official launcher; calls ScriptCaller.sh which sets
#    LD_LIBRARY_PATH for native libs before running dotnet.  Running dotnet directly
#    without this env causes a silent immediate crash.
#    Docker logs will be empty (ScriptCaller.sh pipes dotnet stdout through tee), but
#    the admin panel reads logs from server.log via the file poller instead.
# 2. tModLoaderServer native binary — if present (older releases).
# 3. dotnet tModLoader.dll direct — last resort only.
if [ -f /server/start-tModLoaderServer.sh ]; then
    echo "[terraria-entrypoint] Binary: start-tModLoaderServer.sh"
    exec bash /server/start-tModLoaderServer.sh "${ARGS[@]}" < <(tail -f "$FIFO")
elif [ -f /server/tModLoaderServer ] && [ -x /server/tModLoaderServer ]; then
    echo "[terraria-entrypoint] Binary: tModLoaderServer (native)"
    exec /server/tModLoaderServer "${ARGS[@]}" < <(tail -f "$FIFO")
else
    echo "[terraria-entrypoint] Binary: dotnet tModLoader.dll (fallback)"
    cd /server
    exec dotnet /server/tModLoader.dll -server "${ARGS[@]}" < <(tail -f "$FIFO")
fi

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
# Open FIFO for read+write (O_RDWR) — does not block waiting for a reader,
# unlike O_WRONLY which would hang indefinitely until someone opens the other end.
exec 3<>"$FIFO"

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

# Source tModLoader's environment fix scripts before running dotnet.
#
# BashUtils.sh  — sets $_uname, $_arch, $root_dir used by EnvironmentFix.sh.
# EnvironmentFix.sh — sets LD_LIBRARY_PATH for native libs in /server/Libraries,
#                     fixes SDL/OpenAL env, etc. required for tModLoader native code.
#
# We intentionally skip ScriptCaller.sh to avoid its "download dotnet on crash" loop:
# ScriptCaller.sh deletes $dotnet_dir whenever server.log is missing after a crash,
# which causes it to re-download dotnet on every container restart — an infinite loop.
# The system dotnet (from the base image) is sufficient to run tModLoader.dll.
if [ -f /server/LaunchUtils/BashUtils.sh ]; then
    _prev_dir="$PWD"
    cd /server/LaunchUtils
    set +e
    . ./BashUtils.sh    2>/dev/null
    . ./EnvironmentFix.sh 2>/dev/null
    set -e
    cd "$_prev_dir"
    echo "[terraria-entrypoint] EnvironmentFix sourced (LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-not set})"
fi

if [ -f /server/tModLoader.dll ]; then
    echo "[terraria-entrypoint] Binary: dotnet /server/tModLoader.dll"
    cd /server
    exec dotnet /server/tModLoader.dll -server "${ARGS[@]}" < <(tail -f "$FIFO")
elif [ -f /server/tModLoaderServer ] && [ -x /server/tModLoaderServer ]; then
    echo "[terraria-entrypoint] Binary: /server/tModLoaderServer (native)"
    exec /server/tModLoaderServer "${ARGS[@]}" < <(tail -f "$FIFO")
else
    echo "[terraria-entrypoint] Binary: start-tModLoaderServer.sh (no tModLoader.dll found)"
    exec bash /server/start-tModLoaderServer.sh "${ARGS[@]}" < <(tail -f "$FIFO")
fi

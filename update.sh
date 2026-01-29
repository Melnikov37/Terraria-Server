#!/bin/bash

# TShock Auto-Update Script
# Checks for new version and updates if available

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
VERSION_FILE="$INSTALL_DIR/.tshock_version"
FORCE_UPDATE=false

# Parse arguments
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE_UPDATE=true
fi

echo "=== TShock Update Check ==="

# Get current installed version
CURRENT_VERSION=""
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE")
fi
echo "Current version: ${CURRENT_VERSION:-unknown}"

# Get latest version from GitHub
echo "Checking GitHub for latest release..."
LATEST_RELEASE=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest)
LATEST_VERSION=$(echo "$LATEST_RELEASE" | jq -r '.tag_name')
DOWNLOAD_URL=$(echo "$LATEST_RELEASE" | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)

echo "Latest version: $LATEST_VERSION"

if [ -z "$LATEST_VERSION" ] || [ "$LATEST_VERSION" = "null" ]; then
    echo "Error: Could not fetch latest version from GitHub"
    exit 1
fi

# Check if update needed
if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ] && [ "$FORCE_UPDATE" = false ]; then
    echo "Already up to date!"
    exit 0
fi

echo ""
echo "Update available: $CURRENT_VERSION -> $LATEST_VERSION"
echo "Download URL: $DOWNLOAD_URL"
echo ""

# Check if server is running
SERVER_WAS_RUNNING=false
if systemctl is-active --quiet terraria 2>/dev/null; then
    SERVER_WAS_RUNNING=true
    echo "Stopping server for update..."
    sudo systemctl stop terraria
    sleep 2
fi

# Backup current installation
BACKUP_DIR="$INSTALL_DIR/backups/$(date +%Y%m%d_%H%M%S)"
echo "Creating backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
cp -r "$INSTALL_DIR/ServerPlugins" "$BACKUP_DIR/" 2>/dev/null || true
cp "$INSTALL_DIR/.server_bin" "$BACKUP_DIR/" 2>/dev/null || true

# Download new version
echo "Downloading TShock $LATEST_VERSION..."
cd /tmp
rm -rf tshock-update tshock-update.zip
wget -q --show-progress -O tshock-update.zip "$DOWNLOAD_URL"

# Extract
echo "Extracting..."
mkdir -p tshock-update
unzip -o tshock-update.zip -d tshock-update

# Handle .tar inside .zip
TAR_FILE=$(find tshock-update -name "*.tar" -type f 2>/dev/null | head -1)
if [ -n "$TAR_FILE" ]; then
    echo "Extracting tar archive..."
    tar -xf "$TAR_FILE" -C "$INSTALL_DIR/"
else
    SUBDIR=$(find tshock-update -maxdepth 1 -type d -name "TShock*" | head -1)
    if [ -n "$SUBDIR" ]; then
        cp -r "$SUBDIR"/* "$INSTALL_DIR/"
    else
        cp -r tshock-update/* "$INSTALL_DIR/"
    fi
fi

# Find and set server binary
SERVER_BIN=$(find "$INSTALL_DIR" -name "TShock.Server" -type f 2>/dev/null | head -1)
[ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)
[ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer" -type f -executable 2>/dev/null | head -1)

if [ -n "$SERVER_BIN" ]; then
    chmod +x "$SERVER_BIN"
    echo "$SERVER_BIN" > "$INSTALL_DIR/.server_bin"
    echo "Server binary: $SERVER_BIN"
else
    echo "ERROR: Could not find server binary after update!"
    exit 1
fi

# Save version
echo "$LATEST_VERSION" > "$VERSION_FILE"

# Fix permissions
chown -R terraria:terraria "$INSTALL_DIR"

# Cleanup
rm -rf /tmp/tshock-update /tmp/tshock-update.zip

echo ""
echo "Update complete: $LATEST_VERSION"

# Restart server if it was running
if [ "$SERVER_WAS_RUNNING" = true ]; then
    echo "Restarting server..."
    sudo systemctl start terraria
    sleep 3
    if systemctl is-active --quiet terraria; then
        echo "Server started successfully!"
    else
        echo "Warning: Server may have failed to start. Check: sudo journalctl -u terraria -n 20"
    fi
fi

echo ""
echo "Done!"

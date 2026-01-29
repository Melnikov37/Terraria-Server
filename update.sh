#!/bin/bash

# Terraria Server Auto-Update Script
# Supports both TShock and Vanilla servers

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
VERSION_FILE="$INSTALL_DIR/.server_version"
TYPE_FILE="$INSTALL_DIR/.server_type"
FORCE_UPDATE=false

# Parse arguments
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE_UPDATE=true
fi

echo "=== Terraria Server Update Check ==="

# Get server type
SERVER_TYPE="tshock"
if [ -f "$TYPE_FILE" ]; then
    SERVER_TYPE=$(cat "$TYPE_FILE")
fi
echo "Server type: $SERVER_TYPE"

# Get current version
CURRENT_VERSION=""
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE")
fi
echo "Current version: ${CURRENT_VERSION:-unknown}"

# Get latest version
echo "Checking for updates..."

if [ "$SERVER_TYPE" = "tshock" ]; then
    RELEASE_INFO=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest)
    LATEST_VERSION=$(echo "$RELEASE_INFO" | jq -r '.tag_name')
    DOWNLOAD_URL=$(echo "$RELEASE_INFO" | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)
else
    # Vanilla server
    DOWNLOAD_PAGE=$(curl -s "https://terraria.org/api/get/dedicated-servers-names")
    LATEST_FILE=$(echo "$DOWNLOAD_PAGE" | jq -r '.[0]' 2>/dev/null || echo "")
    if [ -n "$LATEST_FILE" ]; then
        VERSION_NUM=$(echo "$LATEST_FILE" | grep -oP '\d+' | head -1)
        LATEST_VERSION="1.4.5.${VERSION_NUM: -1}"
        DOWNLOAD_URL="https://terraria.org/api/download/pc-dedicated-server/$LATEST_FILE"
    else
        LATEST_VERSION="unknown"
    fi
fi

echo "Latest version: $LATEST_VERSION"

if [ -z "$LATEST_VERSION" ] || [ "$LATEST_VERSION" = "null" ] || [ "$LATEST_VERSION" = "unknown" ]; then
    echo "Error: Could not fetch latest version"
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

# Backup
BACKUP_DIR="$INSTALL_DIR/backups/$(date +%Y%m%d_%H%M%S)"
echo "Creating backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
if [ "$SERVER_TYPE" = "tshock" ]; then
    cp -r "$INSTALL_DIR/ServerPlugins" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "$INSTALL_DIR/tshock" "$BACKUP_DIR/" 2>/dev/null || true
fi
cp "$INSTALL_DIR/.server_bin" "$BACKUP_DIR/" 2>/dev/null || true
cp "$INSTALL_DIR/.server_version" "$BACKUP_DIR/" 2>/dev/null || true

# Download
echo "Downloading $SERVER_TYPE $LATEST_VERSION..."
cd /tmp
rm -rf server-update server-update.zip
wget -q --show-progress -O server-update.zip "$DOWNLOAD_URL"

# Extract
echo "Extracting..."
mkdir -p server-update
unzip -o server-update.zip -d server-update

if [ "$SERVER_TYPE" = "tshock" ]; then
    # Handle .tar inside .zip for TShock
    TAR_FILE=$(find server-update -name "*.tar" -type f 2>/dev/null | head -1)
    if [ -n "$TAR_FILE" ]; then
        tar -xf "$TAR_FILE" -C "$INSTALL_DIR/"
    else
        SUBDIR=$(find server-update -maxdepth 1 -type d -name "TShock*" | head -1)
        if [ -n "$SUBDIR" ]; then
            cp -r "$SUBDIR"/* "$INSTALL_DIR/"
        else
            cp -r server-update/* "$INSTALL_DIR/"
        fi
    fi

    SERVER_BIN=$(find "$INSTALL_DIR" -name "TShock.Server" -type f 2>/dev/null | head -1)
    [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)
else
    # Vanilla server
    LINUX_DIR=$(find server-update -type d -name "Linux" | head -1)
    if [ -n "$LINUX_DIR" ]; then
        cp -r "$LINUX_DIR"/* "$INSTALL_DIR/"
    else
        NUMERIC_DIR=$(find server-update -maxdepth 1 -type d -regex '.*/[0-9]+' | head -1)
        if [ -n "$NUMERIC_DIR" ] && [ -d "$NUMERIC_DIR/Linux" ]; then
            cp -r "$NUMERIC_DIR/Linux"/* "$INSTALL_DIR/"
        fi
    fi

    SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)
    [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer" -type f 2>/dev/null | head -1)
fi

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
rm -rf /tmp/server-update /tmp/server-update.zip

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

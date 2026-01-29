#!/bin/bash

# Terraria Server Installation Script
# Supports both TShock and Vanilla servers
# IDEMPOTENT: Safe to run multiple times

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
SERVER_USER="${SERVER_USER:-terraria}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments
SERVER_TYPE=""
FORCE_DOWNLOAD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tshock|-t)
            SERVER_TYPE="tshock"
            shift
            ;;
        --vanilla|-v)
            SERVER_TYPE="vanilla"
            shift
            ;;
        --update|-u)
            FORCE_DOWNLOAD=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Determine server type
TYPE_FILE="$INSTALL_DIR/.server_type"
if [ -z "$SERVER_TYPE" ]; then
    if [ -f "$TYPE_FILE" ]; then
        SERVER_TYPE=$(cat "$TYPE_FILE")
        echo "Using existing server type: $SERVER_TYPE"
    else
        echo ""
        echo "Choose server type:"
        echo "  1) TShock  - Plugins, permissions, REST API, admin tools (Terraria 1.4.4.9)"
        echo "  2) Vanilla - Official server, latest version (Terraria 1.4.5.x)"
        echo ""
        read -p "Enter choice [1/2]: " choice
        case $choice in
            2|v|vanilla)
                SERVER_TYPE="vanilla"
                ;;
            *)
                SERVER_TYPE="tshock"
                ;;
        esac
    fi
fi

echo ""
echo "=== Terraria Server Installation ==="
echo "Server type: $SERVER_TYPE"
echo "Install directory: $INSTALL_DIR"
echo "Server user: $SERVER_USER"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

# ============================================================
# STEP 1: Install system dependencies
# ============================================================
echo "[1/8] Checking system dependencies..."

PACKAGES="wget unzip screen curl jq python3 python3-venv python3-full"
MISSING=""

for pkg in $PACKAGES; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        MISSING="$MISSING $pkg"
    fi
done

if [ -n "$MISSING" ]; then
    echo "Installing missing packages:$MISSING"
    apt-get update
    apt-get install -y $MISSING
else
    echo "All system packages already installed"
fi

# ============================================================
# STEP 2: Install .NET Runtime (for TShock)
# ============================================================
echo "[2/8] Checking .NET Runtime..."

if [ "$SERVER_TYPE" = "tshock" ]; then
    wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
    chmod +x /tmp/dotnet-install.sh

    if ! dotnet --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 6.0"; then
        echo "Installing .NET 6.0 Runtime (required for TShock)..."
        /tmp/dotnet-install.sh --channel 6.0 --runtime dotnet --install-dir /usr/share/dotnet
    else
        echo ".NET 6.0 already installed"
    fi

    ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet 2>/dev/null || true

    if [ ! -f /etc/profile.d/dotnet.sh ]; then
        echo "export DOTNET_ROOT=/usr/share/dotnet" > /etc/profile.d/dotnet.sh
    fi
    export DOTNET_ROOT=/usr/share/dotnet
    rm -f /tmp/dotnet-install.sh

    echo "Installed .NET runtimes:"
    dotnet --list-runtimes 2>/dev/null || echo "  (none found)"
else
    echo "Skipped (not needed for vanilla)"
fi

# ============================================================
# STEP 3: Create server user
# ============================================================
echo "[3/8] Checking server user..."

if ! id "$SERVER_USER" &>/dev/null; then
    useradd -r -m -d "$INSTALL_DIR" -s /bin/bash "$SERVER_USER"
    echo "Created user: $SERVER_USER"
else
    echo "User already exists: $SERVER_USER"
fi

# ============================================================
# STEP 4: Create directories
# ============================================================
echo "[4/8] Checking directories..."

for dir in "$INSTALL_DIR" "$INSTALL_DIR/worlds" "$INSTALL_DIR/admin" "$INSTALL_DIR/admin/templates" "$INSTALL_DIR/backups"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "Created: $dir"
    fi
done

if [ "$SERVER_TYPE" = "tshock" ]; then
    mkdir -p "$INSTALL_DIR/tshock" "$INSTALL_DIR/ServerPlugins"
fi

# ============================================================
# STEP 5: Download server
# ============================================================
echo "[5/8] Checking server installation..."

CURRENT_TYPE=""
[ -f "$TYPE_FILE" ] && CURRENT_TYPE=$(cat "$TYPE_FILE")

NEED_DOWNLOAD=false
if [ ! -f "$INSTALL_DIR/.server_bin" ]; then
    NEED_DOWNLOAD=true
elif [ "$FORCE_DOWNLOAD" = true ]; then
    NEED_DOWNLOAD=true
elif [ "$CURRENT_TYPE" != "$SERVER_TYPE" ]; then
    NEED_DOWNLOAD=true
    echo "Server type changed: $CURRENT_TYPE -> $SERVER_TYPE"
fi

if [ "$NEED_DOWNLOAD" = true ]; then
    # Stop server if running (to avoid "Text file busy" error)
    if systemctl is-active --quiet terraria 2>/dev/null; then
        echo "Stopping server for update..."
        systemctl stop terraria
        sleep 2
    fi

    cd /tmp
    rm -rf server-extract server-download.*

    if [ "$SERVER_TYPE" = "tshock" ]; then
        echo "Downloading TShock..."
        RELEASE_INFO=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest)
        DOWNLOAD_URL=$(echo "$RELEASE_INFO" | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)
        VERSION=$(echo "$RELEASE_INFO" | jq -r '.tag_name')

        wget -q --show-progress -O server-download.zip "$DOWNLOAD_URL"

        mkdir -p server-extract
        unzip -o server-download.zip -d server-extract

        # Handle .tar inside .zip
        TAR_FILE=$(find server-extract -name "*.tar" -type f 2>/dev/null | head -1)
        if [ -n "$TAR_FILE" ]; then
            tar -xf "$TAR_FILE" -C "$INSTALL_DIR/"
        else
            SUBDIR=$(find server-extract -maxdepth 1 -type d -name "TShock*" | head -1)
            if [ -n "$SUBDIR" ]; then
                cp -r "$SUBDIR"/* "$INSTALL_DIR/"
            else
                cp -r server-extract/* "$INSTALL_DIR/"
            fi
        fi

        # Find binary
        SERVER_BIN=$(find "$INSTALL_DIR" -name "TShock.Server" -type f 2>/dev/null | head -1)
        [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)

        echo "$VERSION" > "$INSTALL_DIR/.server_version"

    else
        echo "Downloading Vanilla server..."
        # Get latest vanilla version
        DOWNLOAD_PAGE=$(curl -s "https://terraria.org/api/get/dedicated-servers-names")
        LATEST_FILE=$(echo "$DOWNLOAD_PAGE" | jq -r '.[0]' 2>/dev/null || echo "terraria-server-1451.zip")
        VERSION=$(echo "$LATEST_FILE" | grep -oP '\d+' | head -1)

        DOWNLOAD_URL="https://terraria.org/api/download/pc-dedicated-server/$LATEST_FILE"
        echo "Downloading: $DOWNLOAD_URL"
        wget -q --show-progress -O server-download.zip "$DOWNLOAD_URL"

        mkdir -p server-extract
        unzip -o server-download.zip -d server-extract

        # Find Linux folder
        LINUX_DIR=$(find server-extract -type d -name "Linux" | head -1)
        if [ -n "$LINUX_DIR" ]; then
            cp -r "$LINUX_DIR"/* "$INSTALL_DIR/"
        else
            # Try numeric folder
            NUMERIC_DIR=$(find server-extract -maxdepth 1 -type d -regex '.*/[0-9]+' | head -1)
            if [ -n "$NUMERIC_DIR" ] && [ -d "$NUMERIC_DIR/Linux" ]; then
                cp -r "$NUMERIC_DIR/Linux"/* "$INSTALL_DIR/"
            fi
        fi

        SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)
        [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer" -type f 2>/dev/null | head -1)

        echo "1.4.5.$VERSION" > "$INSTALL_DIR/.server_version"
    fi

    if [ -n "$SERVER_BIN" ]; then
        chmod +x "$SERVER_BIN"
        echo "$SERVER_BIN" > "$INSTALL_DIR/.server_bin"
        echo "$SERVER_TYPE" > "$TYPE_FILE"
        echo "Server binary: $SERVER_BIN"
        echo "Version: $(cat "$INSTALL_DIR/.server_version")"
    else
        echo "ERROR: Could not find server binary!"
        ls -la "$INSTALL_DIR/"
        exit 1
    fi

    rm -rf server-extract server-download.*
else
    echo "Server already installed: $(cat "$INSTALL_DIR/.server_bin" 2>/dev/null)"
    echo "Version: $(cat "$INSTALL_DIR/.server_version" 2>/dev/null || echo 'unknown')"
fi

# ============================================================
# STEP 6: Create configuration files
# ============================================================
echo "[6/8] Checking configuration files..."

# Server config
if [ ! -f "$INSTALL_DIR/serverconfig.txt" ]; then
    cat > "$INSTALL_DIR/serverconfig.txt" << EOF
# Terraria Server Configuration
world=$INSTALL_DIR/worlds/world1.wld
autocreate=2
worldname=World
difficulty=0
maxplayers=8
port=7777
password=
motd=
worldpath=$INSTALL_DIR/worlds
secure=1
language=en-US
upnp=0
npcstream=60
priority=1
EOF
    echo "Created: serverconfig.txt"
else
    echo "Exists: serverconfig.txt"
fi

# TShock config
if [ "$SERVER_TYPE" = "tshock" ] && [ ! -f "$INSTALL_DIR/tshock/config.json" ]; then
    REST_TOKEN=$(openssl rand -hex 32)

    cat > "$INSTALL_DIR/tshock/config.json" << EOF
{
  "Settings": {
    "ServerPassword": "",
    "ServerPort": 7777,
    "MaxSlots": 8,
    "ReservedSlots": 0,
    "ServerName": "",
    "UseServerName": false,
    "LogPath": "tshock/logs",
    "DebugLogs": false,
    "AutoSave": true,
    "AutoSaveInterval": 10,
    "AnnounceSave": false,
    "EnableWhitelist": false,
    "RequireLogin": false,
    "AllowLoginAnyUsername": true,
    "DisableSpewLogs": true,
    "RESTApiEnabled": true,
    "RESTApiPort": 7878,
    "ApplicationRestTokens": {
      "web-admin": {
        "Username": "web-admin",
        "UserGroupName": "superadmin",
        "Token": "${REST_TOKEN}"
      }
    },
    "StorageType": "sqlite",
    "SqliteDBPath": "tshock/tshock.sqlite",
    "SpawnProtection": false,
    "SuppressPermissionFailureNotices": true,
    "ShowBackupAutosaveMessages": false
  }
}
EOF
    echo "Created: tshock/config.json"
    echo "REST_TOKEN=$REST_TOKEN" > "$INSTALL_DIR/.rest_token"
else
    REST_TOKEN=$(grep -o '"Token": "[^"]*"' "$INSTALL_DIR/tshock/config.json" 2>/dev/null | head -1 | cut -d'"' -f4 || cat "$INSTALL_DIR/.rest_token" 2>/dev/null | cut -d= -f2 || echo "")
fi

# Admin .env file
NEW_INSTALL=false
if [ ! -f "$INSTALL_DIR/admin/.env" ]; then
    NEW_INSTALL=true
    ADMIN_PASSWORD=$(openssl rand -hex 16)
    SECRET_KEY=$(openssl rand -hex 32)
    [ -z "$REST_TOKEN" ] && REST_TOKEN=$(openssl rand -hex 32)

    cat > "$INSTALL_DIR/admin/.env" << EOF
TERRARIA_DIR=$INSTALL_DIR
REST_TOKEN=$REST_TOKEN
REST_URL=http://127.0.0.1:7878
SECRET_KEY=$SECRET_KEY
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMIN_PASSWORD
SERVER_TYPE=$SERVER_TYPE
EOF
    chmod 600 "$INSTALL_DIR/admin/.env"
    echo "Created: admin/.env"
else
    # Update server type in .env
    sed -i "s/^SERVER_TYPE=.*/SERVER_TYPE=$SERVER_TYPE/" "$INSTALL_DIR/admin/.env" 2>/dev/null || \
        echo "SERVER_TYPE=$SERVER_TYPE" >> "$INSTALL_DIR/admin/.env"
    echo "Exists: admin/.env"
fi

# ============================================================
# STEP 7: Setup Python venv and copy admin files
# ============================================================
echo "[7/8] Checking Python environment and admin files..."

# Copy admin files only if source != destination
if [ -d "$SCRIPT_DIR/admin" ] && [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    find "$SCRIPT_DIR/admin" -maxdepth 1 -type f ! -name ".env" -exec cp {} "$INSTALL_DIR/admin/" \;
    cp -r "$SCRIPT_DIR/admin/templates/"* "$INSTALL_DIR/admin/templates/" 2>/dev/null || true
    echo "Updated admin panel files"
fi

if [ ! -d "$INSTALL_DIR/admin/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/admin/venv"
    "$INSTALL_DIR/admin/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/admin/venv/bin/pip" install flask gunicorn requests python-dotenv
    echo "Created: admin/venv"
else
    echo "Exists: admin/venv"
    "$INSTALL_DIR/admin/venv/bin/pip" install -q --upgrade flask gunicorn requests python-dotenv 2>/dev/null || true
fi

# Copy scripts only if source != destination
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    for script in update.sh; do
        if [ -f "$SCRIPT_DIR/$script" ]; then
            cp "$SCRIPT_DIR/$script" "$INSTALL_DIR/$script"
            chmod +x "$INSTALL_DIR/$script"
        fi
    done
fi

chown -R "$SERVER_USER:$SERVER_USER" "$INSTALL_DIR"

# ============================================================
# STEP 8: Setup systemd services
# ============================================================
echo "[8/8] Checking systemd services..."

SERVER_BIN=$(cat "$INSTALL_DIR/.server_bin")

cat > /etc/systemd/system/terraria.service << EOF
[Unit]
Description=Terraria Server ($SERVER_TYPE)
After=network.target

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$INSTALL_DIR
Environment=DOTNET_ROOT=/usr/share/dotnet
ExecStart=$SERVER_BIN -config $INSTALL_DIR/serverconfig.txt
ExecStop=/bin/kill -SIGINT \$MAINPID
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/terraria-admin.service << EOF
[Unit]
Description=Terraria Web Admin Panel
After=network.target terraria.service

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$INSTALL_DIR/admin
EnvironmentFile=$INSTALL_DIR/admin/.env
ExecStart=$INSTALL_DIR/admin/venv/bin/python $INSTALL_DIR/admin/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Sudoers
cat > /etc/sudoers.d/terraria << 'SUDOERS'
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl start terraria
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop terraria
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart terraria
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl status terraria
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl start terraria.service
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop terraria.service
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart terraria.service
terraria ALL=(ALL) NOPASSWD: /usr/bin/systemctl status terraria.service
terraria ALL=(ALL) NOPASSWD: /bin/systemctl start terraria
terraria ALL=(ALL) NOPASSWD: /bin/systemctl stop terraria
terraria ALL=(ALL) NOPASSWD: /bin/systemctl restart terraria
terraria ALL=(ALL) NOPASSWD: /bin/systemctl status terraria
terraria ALL=(ALL) NOPASSWD: /bin/systemctl start terraria.service
terraria ALL=(ALL) NOPASSWD: /bin/systemctl stop terraria.service
terraria ALL=(ALL) NOPASSWD: /bin/systemctl restart terraria.service
terraria ALL=(ALL) NOPASSWD: /bin/systemctl status terraria.service
SUDOERS
chmod 440 /etc/sudoers.d/terraria

systemctl daemon-reload
systemctl enable terraria 2>/dev/null || true
systemctl enable terraria-admin 2>/dev/null || true

# Restart running services
echo ""
echo "Restarting services..."

if systemctl is-active --quiet terraria-admin; then
    systemctl restart terraria-admin
fi

if systemctl is-active --quiet terraria; then
    systemctl restart terraria
fi

# ============================================================
# Done
# ============================================================
echo ""
echo "=========================================="
echo "    Installation Complete!"
echo "=========================================="
echo ""
echo "Server type: $SERVER_TYPE"
echo "Version: $(cat "$INSTALL_DIR/.server_version" 2>/dev/null || echo 'unknown')"
echo "Directory: $INSTALL_DIR"
echo ""

if [ "$NEW_INSTALL" = true ]; then
    echo "========================================"
    echo "  NEW ADMIN CREDENTIALS"
    echo "========================================"
    echo "  URL:      http://your-server-ip:5000"
    echo "  Username: admin"
    echo "  Password: $ADMIN_PASSWORD"
    echo "========================================"
    echo ""
    echo "  SAVE THIS PASSWORD!"
    echo ""
else
    echo "Web Admin: http://your-server-ip:5000"
    echo "Credentials: see $INSTALL_DIR/admin/.env"
    echo ""
fi

echo "Commands:"
echo "  sudo systemctl start terraria        # Start server"
echo "  sudo systemctl start terraria-admin  # Start web admin"
echo ""
echo "Switch server type:"
echo "  sudo ./install.sh --tshock           # Switch to TShock"
echo "  sudo ./install.sh --vanilla          # Switch to Vanilla"
echo ""

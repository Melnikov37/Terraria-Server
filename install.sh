#!/bin/bash

# TShock Terraria Server Installation Script
# IDEMPOTENT: Safe to run multiple times, only adds missing components

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
SERVER_USER="${SERVER_USER:-terraria}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== TShock Terraria Server Installation ==="
echo "Install directory: $INSTALL_DIR"
echo "Server user: $SERVER_USER"
echo "Mode: Idempotent (safe to re-run)"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

# ============================================================
# STEP 1: Install system dependencies (idempotent by default)
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
# STEP 2: Install .NET Runtime
# ============================================================
echo "[2/8] Checking .NET Runtime..."

if ! command -v dotnet &> /dev/null; then
    echo "Installing .NET Runtime..."
    wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
    chmod +x /tmp/dotnet-install.sh
    /tmp/dotnet-install.sh --channel 8.0 --runtime dotnet --install-dir /usr/share/dotnet
    ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet

    if [ ! -f /etc/profile.d/dotnet.sh ]; then
        echo "export DOTNET_ROOT=/usr/share/dotnet" > /etc/profile.d/dotnet.sh
    fi
    export DOTNET_ROOT=/usr/share/dotnet
    rm -f /tmp/dotnet-install.sh
else
    echo ".NET Runtime already installed: $(dotnet --version 2>/dev/null || echo 'unknown version')"
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

for dir in "$INSTALL_DIR" "$INSTALL_DIR/worlds" "$INSTALL_DIR/tshock" "$INSTALL_DIR/ServerPlugins" "$INSTALL_DIR/admin" "$INSTALL_DIR/admin/templates"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "Created: $dir"
    fi
done

# ============================================================
# STEP 5: Download TShock (only if not present or update requested)
# ============================================================
echo "[5/8] Checking TShock installation..."

NEED_DOWNLOAD=false

if [ ! -f "$INSTALL_DIR/.server_bin" ]; then
    NEED_DOWNLOAD=true
    echo "TShock not found, will download..."
elif [ "$1" = "--update" ] || [ "$1" = "-u" ]; then
    NEED_DOWNLOAD=true
    echo "Update requested, will re-download TShock..."
else
    SERVER_BIN=$(cat "$INSTALL_DIR/.server_bin" 2>/dev/null || echo "")
    if [ ! -f "$SERVER_BIN" ]; then
        NEED_DOWNLOAD=true
        echo "Server binary missing, will re-download..."
    else
        echo "TShock already installed: $SERVER_BIN"
    fi
fi

if [ "$NEED_DOWNLOAD" = true ]; then
    cd /tmp

    # Get latest release URL
    DOWNLOAD_URL=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)

    if [ -z "$DOWNLOAD_URL" ]; then
        echo "Error: Could not find TShock download URL"
        exit 1
    fi

    echo "Downloading: $DOWNLOAD_URL"
    wget -q --show-progress -O tshock-download.zip "$DOWNLOAD_URL"

    # Extract
    rm -rf tshock-extract
    mkdir -p tshock-extract
    unzip -o tshock-download.zip -d tshock-extract

    # Handle .tar inside .zip
    TAR_FILE=$(find tshock-extract -name "*.tar" -type f 2>/dev/null | head -1)
    if [ -n "$TAR_FILE" ]; then
        echo "Extracting tar: $TAR_FILE"
        tar -xf "$TAR_FILE" -C "$INSTALL_DIR/"
    else
        SUBDIR=$(find tshock-extract -maxdepth 1 -type d -name "TShock*" | head -1)
        if [ -n "$SUBDIR" ]; then
            cp -r "$SUBDIR"/* "$INSTALL_DIR/"
        else
            cp -r tshock-extract/* "$INSTALL_DIR/"
        fi
    fi

    # Find server binary
    SERVER_BIN=$(find "$INSTALL_DIR" -name "TShock.Server" -type f 2>/dev/null | head -1)
    [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer.bin.x86_64" -type f 2>/dev/null | head -1)
    [ -z "$SERVER_BIN" ] && SERVER_BIN=$(find "$INSTALL_DIR" -name "TerrariaServer" -type f -executable 2>/dev/null | head -1)

    if [ -n "$SERVER_BIN" ]; then
        chmod +x "$SERVER_BIN"
        echo "$SERVER_BIN" > "$INSTALL_DIR/.server_bin"
        echo "Server binary: $SERVER_BIN"
    else
        echo "ERROR: Could not find server binary!"
        ls -la "$INSTALL_DIR/"
        exit 1
    fi

    rm -rf tshock-download.zip tshock-extract
fi

# ============================================================
# STEP 6: Create configuration files (only if not exist)
# ============================================================
echo "[6/8] Checking configuration files..."

# Server config
if [ ! -f "$INSTALL_DIR/serverconfig.txt" ]; then
    cat > "$INSTALL_DIR/serverconfig.txt" << 'EOF'
# TShock Server Configuration (Vanilla-like)
world=/opt/terraria/worlds/world1.wld
autocreate=2
worldname=World
difficulty=0
maxplayers=8
port=7777
password=
motd=
worldpath=/opt/terraria/worlds
secure=1
language=en-US
upnp=0
npcstream=60
priority=1
EOF
    echo "Created: serverconfig.txt"
else
    echo "Exists: serverconfig.txt (not modified)"
fi

# TShock config - only create if not exists
if [ ! -f "$INSTALL_DIR/tshock/config.json" ]; then
    # Generate tokens only for new installation
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
    "DisableLoginBeforeJoin": false,
    "IgnoreChestStacksOnLoad": false,
    "AutoSave": true,
    "AutoSaveInterval": 10,
    "AnnounceSave": false,
    "EnableWhitelist": false,
    "WhitelistKickReason": "You are not on the whitelist.",
    "HardcoreOnly": false,
    "MediumcoreOnly": false,
    "SoftcoreOnly": false,
    "DisableBuild": false,
    "DisableClownBombs": false,
    "DisableDungeonGuardian": false,
    "DisableInvisPvP": false,
    "DisableSnowBalls": false,
    "DisableTombstones": false,
    "ForceTime": "normal",
    "PvPMode": "normal",
    "SpawnProtection": false,
    "SpawnProtectionRadius": 10,
    "RangeChecks": true,
    "AnonymousBossInvasions": true,
    "MaxHP": 500,
    "MaxMP": 200,
    "BombExplosionRadius": 5,
    "DefaultRegistrationGroupName": "default",
    "DefaultGuestGroupName": "guest",
    "RememberLeavePos": false,
    "MaximumLoginAttempts": 3,
    "KickOnMediumcoreDeath": false,
    "BanOnMediumcoreDeath": false,
    "RequireLogin": false,
    "AllowLoginAnyUsername": true,
    "AllowRegisterAnyUsername": true,
    "DisableUUIDLogin": false,
    "KickEmptyUUID": false,
    "DisableSpewLogs": true,
    "HashAlgorithm": "sha512",
    "BCryptWorkFactor": 7,
    "RESTApiEnabled": true,
    "RESTApiPort": 7878,
    "RESTRequestBucketDecreaseIntervalMinutes": 1,
    "RESTLimitOnlyFailedLoginRequests": true,
    "RESTMaximumRequestsPerInterval": 5,
    "LogRest": false,
    "EnableTokenEndpointAuthentication": false,
    "RESTMaximumRequestBodySize": 8000,
    "ApplicationRestTokens": {
      "web-admin": {
        "Username": "web-admin",
        "UserGroupName": "superadmin",
        "Token": "${REST_TOKEN}"
      }
    },
    "BroadcastRGB": [127, 255, 212],
    "StorageType": "sqlite",
    "SqliteDBPath": "tshock/tshock.sqlite",
    "UseSqlLogs": false,
    "PreventBannedItemSpawn": false,
    "PreventDeadModification": true,
    "PreventInvalidPlaceStyle": true,
    "ForceXmas": false,
    "ForceHalloween": false,
    "AllowCutTilesAndBreakables": false,
    "AllowIce": false,
    "AllowCrimsonCreep": true,
    "AllowCorruptionCreep": true,
    "AllowHallowCreep": true,
    "StatueSpawn200": 3,
    "StatueSpawn600": 6,
    "StatueSpawnWorld": 10,
    "CommandSpecifier": "/",
    "CommandSilentSpecifier": ".",
    "KickOnHardcoreDeath": false,
    "BanOnHardcoreDeath": false,
    "DisableDefaultIPBan": false,
    "EnableIPBans": true,
    "EnableUUIDBans": true,
    "EnableBanOnUsernames": false,
    "DefaultMaximumSpawns": 5,
    "DefaultSpawnRate": 600,
    "InfiniteInvasion": false,
    "PvPWithoutArmor": true,
    "EnableChatAboveHeads": false,
    "EnableGeoIP": false,
    "DisplayIPToAdmins": false,
    "ChatFormat": "{1}{2}{3}: {4}",
    "ChatAboveHeadsFormat": "{2}",
    "SuppressPermissionFailureNotices": true,
    "DisableSecondUpdateLogs": true,
    "SuperAdminChatRGB": [255, 255, 255],
    "SuperAdminChatPrefix": "",
    "SuperAdminChatSuffix": "",
    "ShowBackupAutosaveMessages": false
  }
}
EOF
    echo "Created: tshock/config.json"
    echo "REST_TOKEN=$REST_TOKEN" > "$INSTALL_DIR/.rest_token"
else
    echo "Exists: tshock/config.json (not modified)"
    # Extract existing REST token for admin .env
    REST_TOKEN=$(grep -o '"Token": "[^"]*"' "$INSTALL_DIR/tshock/config.json" | head -1 | cut -d'"' -f4 || cat "$INSTALL_DIR/.rest_token" 2>/dev/null | cut -d= -f2 || echo "")
fi

# Admin .env file
NEW_INSTALL=false
if [ ! -f "$INSTALL_DIR/admin/.env" ]; then
    NEW_INSTALL=true
    ADMIN_PASSWORD=$(openssl rand -hex 16)
    SECRET_KEY=$(openssl rand -hex 32)

    # Use existing REST_TOKEN if available
    if [ -z "$REST_TOKEN" ]; then
        REST_TOKEN=$(openssl rand -hex 32)
        echo "Warning: Generated new REST token. Update tshock/config.json manually."
    fi

    cat > "$INSTALL_DIR/admin/.env" << EOF
TERRARIA_DIR=$INSTALL_DIR
REST_TOKEN=$REST_TOKEN
REST_URL=http://127.0.0.1:7878
SECRET_KEY=$SECRET_KEY
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF
    chmod 600 "$INSTALL_DIR/admin/.env"
    echo "Created: admin/.env"
else
    echo "Exists: admin/.env (credentials preserved)"
fi

# ============================================================
# STEP 7: Setup Python venv and copy admin files
# ============================================================
echo "[7/8] Checking Python environment and admin files..."

# Copy admin files (always update code, but not .env)
if [ -d "$SCRIPT_DIR/admin" ]; then
    # Copy all except .env and venv
    find "$SCRIPT_DIR/admin" -maxdepth 1 -type f ! -name ".env" -exec cp {} "$INSTALL_DIR/admin/" \;
    cp -r "$SCRIPT_DIR/admin/templates/"* "$INSTALL_DIR/admin/templates/" 2>/dev/null || true
    echo "Updated admin panel files"
fi

# Create venv if not exists
if [ ! -d "$INSTALL_DIR/admin/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/admin/venv"
    "$INSTALL_DIR/admin/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/admin/venv/bin/pip" install flask gunicorn requests python-dotenv
    echo "Created: admin/venv"
else
    echo "Exists: admin/venv"
    # Update packages
    "$INSTALL_DIR/admin/venv/bin/pip" install -q --upgrade flask gunicorn requests python-dotenv 2>/dev/null || true
fi

# Fix ownership
chown -R "$SERVER_USER:$SERVER_USER" "$INSTALL_DIR"

# ============================================================
# STEP 8: Setup systemd services and sudoers
# ============================================================
echo "[8/8] Checking systemd services..."

SERVER_BIN=$(cat "$INSTALL_DIR/.server_bin")

# Terraria service
if [ ! -f /etc/systemd/system/terraria.service ] || [ "$1" = "--update" ]; then
    cat > /etc/systemd/system/terraria.service << EOF
[Unit]
Description=TShock Terraria Server
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
    echo "Created/Updated: terraria.service"
    RELOAD_SYSTEMD=true
else
    echo "Exists: terraria.service"
fi

# Admin service
if [ ! -f /etc/systemd/system/terraria-admin.service ] || [ "$1" = "--update" ]; then
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
    echo "Created/Updated: terraria-admin.service"
    RELOAD_SYSTEMD=true
else
    echo "Exists: terraria-admin.service"
fi

# Sudoers - allow terraria user to run systemctl for terraria services
echo "Updating sudoers configuration..."
cat > /etc/sudoers.d/terraria << 'SUDOERS'
# Allow terraria user to manage services without password
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
# Validate sudoers syntax
if visudo -c -f /etc/sudoers.d/terraria 2>/dev/null; then
    echo "Updated: sudoers.d/terraria (validated)"
else
    echo "ERROR: sudoers syntax error!"
    cat /etc/sudoers.d/terraria
fi

# Reload systemd if needed
if [ "$RELOAD_SYSTEMD" = true ]; then
    systemctl daemon-reload
fi

# Enable services (idempotent)
systemctl enable terraria 2>/dev/null || true
systemctl enable terraria-admin 2>/dev/null || true

echo ""
echo "=========================================="
echo "    Installation Complete!"
echo "=========================================="
echo ""
echo "Server: $INSTALL_DIR"
echo "Config: $INSTALL_DIR/serverconfig.txt"
echo "Worlds: $INSTALL_DIR/worlds/"
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
echo "  sudo systemctl start terraria        # Start game server"
echo "  sudo systemctl start terraria-admin  # Start web admin"
echo "  sudo systemctl status terraria       # Check status"
echo ""
echo "Re-run options:"
echo "  ./install.sh           # Safe re-run, preserves configs"
echo "  ./install.sh --update  # Re-download TShock & update services"
echo ""

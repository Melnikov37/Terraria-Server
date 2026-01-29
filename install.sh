#!/bin/bash

# TShock Terraria Server Installation Script for Linux (Debian/Ubuntu)
# Configured for "vanilla-like" experience with full web management

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
SERVER_USER="${SERVER_USER:-terraria}"
TSHOCK_VERSION="${TSHOCK_VERSION:-v5.2.0}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -hex 16)}"
REST_TOKEN="${REST_TOKEN:-$(openssl rand -hex 32)}"

echo "=== TShock Terraria Server Installation ==="
echo "Install directory: $INSTALL_DIR"
echo "Server user: $SERVER_USER"
echo "TShock version: $TSHOCK_VERSION"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

# Install dependencies
echo "[1/8] Installing dependencies..."
apt-get update
apt-get install -y wget unzip screen curl jq python3 python3-pip

# Install .NET Runtime (required for TShock)
echo "[2/8] Installing .NET Runtime..."
if ! command -v dotnet &> /dev/null; then
    wget https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
    chmod +x /tmp/dotnet-install.sh
    /tmp/dotnet-install.sh --channel 8.0 --runtime dotnet --install-dir /usr/share/dotnet
    ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet
    echo "export DOTNET_ROOT=/usr/share/dotnet" >> /etc/profile.d/dotnet.sh
    export DOTNET_ROOT=/usr/share/dotnet
else
    echo ".NET Runtime already installed"
fi

# Create server user if doesn't exist
echo "[3/8] Creating server user..."
if ! id "$SERVER_USER" &>/dev/null; then
    useradd -r -m -d "$INSTALL_DIR" -s /bin/bash "$SERVER_USER"
    echo "User '$SERVER_USER' created"
else
    echo "User '$SERVER_USER' already exists"
fi

# Create install directory
echo "[4/8] Creating install directory..."
mkdir -p "$INSTALL_DIR"

# Download TShock
echo "[5/8] Downloading TShock $TSHOCK_VERSION..."
cd /tmp

if [ "$TSHOCK_VERSION" = "latest" ]; then
    DOWNLOAD_URL=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)
else
    DOWNLOAD_URL="https://github.com/Pryaxis/TShock/releases/download/${TSHOCK_VERSION}/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release.zip"
fi

echo "Downloading from: $DOWNLOAD_URL"
wget -q --show-progress -O tshock.zip "$DOWNLOAD_URL"

# Extract server files
echo "[6/8] Extracting TShock files..."
rm -rf tshock-extract
unzip -o tshock.zip -d tshock-extract

if [ -d "tshock-extract/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release" ]; then
    cp -r tshock-extract/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release/* "$INSTALL_DIR/"
else
    cp -r tshock-extract/* "$INSTALL_DIR/"
fi

chmod +x "$INSTALL_DIR/TShock.Server"
rm -rf tshock.zip tshock-extract

# Create directories
mkdir -p "$INSTALL_DIR/worlds"
mkdir -p "$INSTALL_DIR/tshock"
mkdir -p "$INSTALL_DIR/ServerPlugins"
mkdir -p "$INSTALL_DIR/admin"

# Create server config
echo "[7/8] Creating configuration files..."
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

# Create TShock config for vanilla-like experience
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
    "HardcoreBanReason": "Death results in a ban",
    "HardcoreKickReason": "Death results in a kick",
    "MediumcoreBanReason": "Death results in a ban",
    "MediumcoreKickReason": "Death results in a kick",

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
    "DisablePrimaryUUIDLogin": false,

    "RESTApiEnabled": true,
    "RESTApiPort": 7878,
    "RESTRequestBucketDecreaseIntervalMinutes": 1,
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
    "MySqlHost": "localhost:3306",
    "MySqlDbName": "",
    "MySqlUsername": "",
    "MySqlPassword": "",

    "UseSqlLogs": false,
    "RevertToTextLogsOnSqlFailures": 10,

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
    "PreventBannedItemSpawn": false,

    "CommandSpecifier": "/",
    "CommandSilentSpecifier": ".",
    "KickOnHardcoreDeath": false,
    "BanOnHardcoreDeath": false,
    "DisableDefaultIPBan": false,
    "EnableDNSHostResolution": false,
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
    "AvailableSlotNotification": false,
    "AvailableSlotsNotification": false,

    "CommandTextColor": [255, 255, 0],

    "SuppressPermissionFailureNotices": true,
    "DisableSecondUpdateLogs": true,
    "SuperAdminChatRGB": [255, 255, 255],
    "SuperAdminChatPrefix": "",
    "SuperAdminChatSuffix": "",

    "DisableModifiedArmorCheck": false,
    "DisableViableCrystalCheck": false,
    "DisableTileKillCheck": false,
    "DisableTilePlaceCheck": false,
    "DisableBuilderCheck": false,
    "DisableGuardCheck": false,
    "DisableFireCheck": false,
    "DisableHardmodeCheck": false,
    "DisableTileRangeCheck": false,
    "DisableDamageCheck": false,
    "DisableEmoteCheck": false,
    "DisablePossibleExplosionCheck": false,
    "DisableNPCSpawnCheck": false,
    "DisableProjectileCheck": false,
    "DisableHealOtherCheck": false,
    "DisablePlaceUnfitCheck": false,
    "DisablePortalCheck": false,
    "DisableHostilePossessionCheck": false,

    "ShowBackupAutosaveMessages": false
  }
}
EOF

# Create credentials file for web admin
cat > "$INSTALL_DIR/admin/.env" << EOF
TERRARIA_DIR=$INSTALL_DIR
REST_TOKEN=$REST_TOKEN
REST_URL=http://127.0.0.1:7878
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF

# Set permissions
chown -R "$SERVER_USER:$SERVER_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/admin/.env"

# Create systemd service for TShock
echo "[8/8] Creating systemd services..."
cat > /etc/systemd/system/terraria.service << EOF
[Unit]
Description=TShock Terraria Server
After=network.target

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$INSTALL_DIR
Environment=DOTNET_ROOT=/usr/share/dotnet
ExecStart=$INSTALL_DIR/TShock.Server -config $INSTALL_DIR/serverconfig.txt
ExecStop=/bin/kill -SIGINT \$MAINPID
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for web admin
cat > /etc/systemd/system/terraria-admin.service << EOF
[Unit]
Description=Terraria Web Admin Panel
After=network.target terraria.service

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$INSTALL_DIR/admin
EnvironmentFile=$INSTALL_DIR/admin/.env
ExecStart=/usr/bin/python3 $INSTALL_DIR/admin/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable terraria
systemctl enable terraria-admin

# Copy admin files
cp -r "$(dirname "$0")/admin/"* "$INSTALL_DIR/admin/" 2>/dev/null || true
chown -R "$SERVER_USER:$SERVER_USER" "$INSTALL_DIR/admin"

# Install Python dependencies
pip3 install flask gunicorn requests python-dotenv

echo ""
echo "=========================================="
echo "    Installation Complete!"
echo "=========================================="
echo ""
echo "Server configured for VANILLA-LIKE experience:"
echo "  - No login/registration required"
echo "  - No TShock messages visible to players"
echo "  - All management via Web Admin"
echo ""
echo "Web Admin Credentials:"
echo "  URL:      http://your-server-ip:5000"
echo "  Username: admin"
echo "  Password: $ADMIN_PASSWORD"
echo ""
echo "SAVE THESE CREDENTIALS! They are stored in:"
echo "  $INSTALL_DIR/admin/.env"
echo ""
echo "Commands:"
echo "  sudo systemctl start terraria        # Start game server"
echo "  sudo systemctl start terraria-admin  # Start web admin"
echo "  sudo systemctl status terraria       # Check status"
echo ""
echo "Quick start:"
echo "  sudo systemctl start terraria && sudo systemctl start terraria-admin"
echo ""

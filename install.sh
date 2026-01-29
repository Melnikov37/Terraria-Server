#!/bin/bash

# TShock Terraria Server Installation Script for Linux (Debian/Ubuntu)
# Downloads and installs TShock - advanced Terraria server with plugins support

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/terraria}"
SERVER_USER="${SERVER_USER:-terraria}"
TSHOCK_VERSION="${TSHOCK_VERSION:-v5.2.0}"

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
echo "[1/7] Installing dependencies..."
apt-get update
apt-get install -y wget unzip screen curl jq

# Install .NET Runtime (required for TShock)
echo "[2/7] Installing .NET Runtime..."
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
echo "[3/7] Creating server user..."
if ! id "$SERVER_USER" &>/dev/null; then
    useradd -r -m -d "$INSTALL_DIR" -s /bin/bash "$SERVER_USER"
    echo "User '$SERVER_USER' created"
else
    echo "User '$SERVER_USER' already exists"
fi

# Create install directory
echo "[4/7] Creating install directory..."
mkdir -p "$INSTALL_DIR"

# Download TShock
echo "[5/7] Downloading TShock $TSHOCK_VERSION..."
cd /tmp

# Get download URL from GitHub API
if [ "$TSHOCK_VERSION" = "latest" ]; then
    DOWNLOAD_URL=$(curl -s https://api.github.com/repos/Pryaxis/TShock/releases/latest | jq -r '.assets[] | select(.name | contains("linux")) | .browser_download_url' | head -1)
else
    DOWNLOAD_URL="https://github.com/Pryaxis/TShock/releases/download/${TSHOCK_VERSION}/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release.zip"
fi

echo "Downloading from: $DOWNLOAD_URL"
wget -q --show-progress -O tshock.zip "$DOWNLOAD_URL"

# Extract server files
echo "[6/7] Extracting TShock files..."
rm -rf tshock-extract
unzip -o tshock.zip -d tshock-extract

# Find and copy files (TShock archives have varying structure)
if [ -d "tshock-extract/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release" ]; then
    cp -r tshock-extract/TShock-5.2-for-Terraria-1.4.4.9-linux-x64-Release/* "$INSTALL_DIR/"
else
    cp -r tshock-extract/* "$INSTALL_DIR/"
fi

chmod +x "$INSTALL_DIR/TShock.Server"

# Clean up
rm -rf tshock.zip tshock-extract

# Create directories
mkdir -p "$INSTALL_DIR/worlds"
mkdir -p "$INSTALL_DIR/tshock"
mkdir -p "$INSTALL_DIR/ServerPlugins"

# Create default config if not exists
if [ ! -f "$INSTALL_DIR/serverconfig.txt" ]; then
    cat > "$INSTALL_DIR/serverconfig.txt" << 'EOF'
# TShock Server Configuration
# Full documentation: https://ikebukuro.tshock.co/

# World settings
world=/opt/terraria/worlds/world1.wld
autocreate=2
worldname=MyWorld
difficulty=0
seed=

# Server settings
maxplayers=8
port=7777
password=
motd=Welcome to TShock Server!
worldpath=/opt/terraria/worlds

# Security
secure=1
language=en-US
upnp=0
npcstream=60
priority=1
EOF
fi

# Set permissions
chown -R "$SERVER_USER:$SERVER_USER" "$INSTALL_DIR"

# Create systemd service
echo "[7/7] Creating systemd service..."
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

systemctl daemon-reload
systemctl enable terraria

echo ""
echo "=========================================="
echo "    TShock Installation Complete!"
echo "=========================================="
echo ""
echo "Directories:"
echo "  Server:     $INSTALL_DIR"
echo "  Worlds:     $INSTALL_DIR/worlds"
echo "  Plugins:    $INSTALL_DIR/ServerPlugins"
echo "  TShock:     $INSTALL_DIR/tshock"
echo ""
echo "Configuration:"
echo "  Server:     $INSTALL_DIR/serverconfig.txt"
echo "  TShock:     $INSTALL_DIR/tshock/config.json (created on first run)"
echo ""
echo "Commands:"
echo "  sudo systemctl start terraria    # Start server"
echo "  sudo systemctl stop terraria     # Stop server"
echo "  sudo systemctl restart terraria  # Restart server"
echo "  sudo systemctl status terraria   # Check status"
echo "  sudo journalctl -u terraria -f   # View logs"
echo ""
echo "First run:"
echo "  1. Start the server: sudo systemctl start terraria"
echo "  2. Check logs for setup token: sudo journalctl -u terraria | grep token"
echo "  3. Join the server and use: /setup <token>"
echo "  4. Create admin: /user add <username> <password> superadmin"
echo ""
echo "Web Admin Panel:"
echo "  cd $INSTALL_DIR/admin"
echo "  pip3 install -r requirements.txt"
echo "  python3 app.py"
echo ""
echo "REST API (after first run):"
echo "  http://localhost:7878/v3/server/status"
echo ""

FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /server

# Download tModLoader. Override version with: --build-arg TMODLOADER_VERSION=v2024.x.y.z
ARG TMODLOADER_VERSION=v2025.12.3.0
RUN wget -q \
      "https://github.com/tModLoader/tModLoader/releases/download/${TMODLOADER_VERSION}/tModLoader.zip" \
      -O /tmp/tModLoader.zip \
    && unzip -q /tmp/tModLoader.zip -d /server \
    && rm /tmp/tModLoader.zip \
    && find /server -maxdepth 1 -name "*.sh" -exec chmod +x {} \; \
    && (chmod +x /server/tModLoaderServer 2>/dev/null || true)

COPY server-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Game port (TCP + UDP)
EXPOSE 7777/tcp
EXPOSE 7777/udp

ENTRYPOINT ["/entrypoint.sh"]

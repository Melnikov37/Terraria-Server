FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget unzip curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /server

# Set to a specific tag (e.g. v2025.12.3.0) to pin, or leave "latest" to auto-resolve.
ARG TMODLOADER_VERSION=latest
RUN if [ "$TMODLOADER_VERSION" = "latest" ]; then \
      TMODLOADER_VERSION=$(curl -fsSL \
        "https://api.github.com/repos/tModLoader/tModLoader/releases/latest" \
        | jq -r '.tag_name'); \
    fi \
    && echo "Installing tModLoader ${TMODLOADER_VERSION}" \
    && wget -q \
         "https://github.com/tModLoader/tModLoader/releases/download/${TMODLOADER_VERSION}/tModLoader.zip" \
         -O /tmp/tModLoader.zip \
    && unzip -q /tmp/tModLoader.zip -d /server \
    && rm /tmp/tModLoader.zip \
    && find /server -maxdepth 1 -name "*.sh" -exec chmod +x {} \; \
    && (chmod +x /server/tModLoaderServer 2>/dev/null || true) \
    && echo "${TMODLOADER_VERSION}" > /server/version.txt

COPY server-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Game port (TCP + UDP)
EXPOSE 7777/tcp
EXPOSE 7777/udp

ENTRYPOINT ["/entrypoint.sh"]

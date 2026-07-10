# ============================
# 1. BUILDER STAGE
# ============================


FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

ENV ROOT_PROJ_DIR=/app

WORKDIR $ROOT_PROJ_DIR

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy
# Force uv to create the .venv in a specific, predictable location
ENV UV_PROJECT_ENVIRONMENT=/opt/uv/.venv


COPY pyproject.toml ./

# Install base build packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    git \
    ssh \
    && rm -rf /var/lib/apt/lists/*

#WORKDIR $PYSETUP_PATH
RUN --mount=type=secret,id=ssh_private_key \
    mkdir -p -m 0700 /root/.ssh && \
    echo "Host *\n\tStrictHostKeyChecking no\n" > /root/.ssh/config && \
    cp /run/secrets/ssh_private_key /root/.ssh/id_rsa && \
    chmod 600 /root/.ssh/id_rsa

# Install external dependencies, leveraging cache for faster builds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# copy only what you need (thanks to .dockerignore)
COPY . .

# If the pyproject.toml and the lockfile (uv.lock) are out of sync, the command will fail rather than trying to fix them.
# This ensures the environment is built using the exact versions previously tested.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --group wrappers --group docs

# Clean up keys immediately after use in this layer
RUN rm -rf ~/.ssh

# ============================
# 2. FINAL STAGE
# ============================
#FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
FROM python:3.12-slim AS wrapster

ENV ROOT_PROJ_DIR=/app

ENV PATH="/opt/uv/.venv/bin:$PATH"

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d $ROOT_PROJ_DIR -s /bin/false appuser

WORKDIR $ROOT_PROJ_DIR

COPY --from=build --chown=appuser:appgroup $ROOT_PROJ_DIR .
COPY --from=build --chown=appuser:appgroup /opt/uv/.venv /opt/uv/.venv

USER appuser

RUN chmod +x ./workers.sh ./start.sh

# Run the start.sh script as the container's default command
CMD ["./start.sh"]

# ============================
# 3. MKDOCS STAGE
# ============================
FROM python:3.12-slim AS mkdocs

ARG PORT=7000
ENV MKDOCS_PORT=${PORT}
ENV ROOT_PROJ_DIR=/app

ENV PATH="/opt/uv/.venv/bin:$PATH"

# Install MkDocs-specific system dependencies [cite: 7, 8]
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    chromium \
    fonts-freefont-ttf \
    fonts-noto \
    fontconfig \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy fonts and app from build [cite: 7]
COPY fonts /usr/share/fonts/Additional
RUN fc-cache -f

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d $ROOT_PROJ_DIR -s /bin/false appuser

WORKDIR $ROOT_PROJ_DIR

COPY --from=build --chown=appuser:appgroup $ROOT_PROJ_DIR .
COPY --from=build --chown=appuser:appgroup /opt/uv/.venv /opt/uv/.venv

USER appuser

EXPOSE ${MKDOCS_PORT}

COPY --chmod=755 docker-entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
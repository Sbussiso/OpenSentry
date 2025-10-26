# OpenSentry - SMV (Snapshot Motion Version) Dockerfile
# Optimized for low-power devices like Raspberry Pi Zero W
# Follows uv Docker guide patterns:
# https://docs.astral.sh/uv/guides/integration/docker/

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build tools and common runtime libs
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    git \
    libopenblas-dev \
    liblapack-dev \
    libatlas-base-dev \
    libturbojpeg0 \
    libjpeg62-turbo \
    libpng16-16 \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies with uv sync using the lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync

# Copy sources to allow any post-install steps (not strictly required for build stage)
COPY . .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install only runtime libraries (no build tools)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libopenblas-dev \
    liblapack-dev \
    libatlas-base-dev \
    libturbojpeg0 \
    libjpeg62-turbo \
    libpng16-16 \
    libglib2.0-0 \
    libgl1 \
    libv4l-0 \
    v4l-utils \
 && rm -rf /var/lib/apt/lists/*

# Copy virtualenv and app sources
COPY --from=build /app/.venv /app/.venv
COPY . .

# Use venv binaries directly
ENV PATH="/app/.venv/bin:${PATH}"

# Fix venv interpreter symlink path: ensure /usr/bin/python3.12 resolves
# Some uv base variants install python at /usr/local/bin/python3 only.
RUN ln -sf /usr/local/bin/python3 /usr/bin/python3.12 || true

# Create snapshots directory and declare as volume for persistence
RUN mkdir -p /app/snapshots
VOLUME ["/app/snapshots"]

EXPOSE 5000

# Defaults for runtime (snapshot-only mode)
ENV OPENSENTRY_PORT=5000 \
    OPENSENTRY_SNAPSHOT_INTERVAL=10 \
    OPENSENTRY_JPEG_QUALITY=75 \
    GUNICORN_WORKERS=1 \
    GUNICORN_WORKER_CLASS=sync \
    GUNICORN_TIMEOUT=120 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_CORETYPE=ARMV8

# Ensure the uv base image ENTRYPOINT does not wrap our command
ENTRYPOINT []

# Run the app via uv (uses the pre-synced project environment; --frozen prevents resolution)
CMD ["sh", "-c", "uv run --frozen -m gunicorn -w ${GUNICORN_WORKERS:-1} -k ${GUNICORN_WORKER_CLASS:-sync} --timeout ${GUNICORN_TIMEOUT:-120} --bind 0.0.0.0:${OPENSENTRY_PORT:-5000} server:app"]

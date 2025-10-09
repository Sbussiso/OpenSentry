# OpenSentry Dockerfile (uv + Pi-ready)
# Follows uv Docker guide patterns:
# https://docs.astral.sh/uv/guides/integration/docker/

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build tools and common runtime libs (cmake required for dlib on ARM)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    git \
    libopenblas-dev \
    liblapack-dev \
    libatlas-base-dev \
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
    libjpeg62-turbo \
    libpng16-16 \
    libglib2.0-0 \
    libgl1 \
 && rm -rf /var/lib/apt/lists/*

# Copy virtualenv and app sources
COPY --from=build /app/.venv /app/.venv
COPY . .

# Use venv binaries directly
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 5000
VOLUME ["/app/archives"]

# Defaults for runtime
ENV OPENSENTRY_PORT=5000 \
    GUNICORN_WORKERS=2 \
    GUNICORN_TIMEOUT=60

# Run gunicorn directly from the venv
CMD ["sh", "-c", "gunicorn -w ${GUNICORN_WORKERS:-2} -k gevent --timeout ${GUNICORN_TIMEOUT:-60} --bind 0.0.0.0:${OPENSENTRY_PORT:-5000} server:app"]

# OpenSentry Dockerfile (uv + Pi-ready)
# Follows uv Docker guide patterns:
# https://docs.astral.sh/uv/guides/integration/docker/

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

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
RUN uv sync --locked

# Copy the project (sources only) after deps for better layer cache
COPY . .

EXPOSE 5000
VOLUME ["/app/archives"]

# Run via uv (uses the environment created by `uv sync`)
CMD ["uv", "run", "server.py"]

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

# (No source copy needed in build stage; we only need the venv from uv sync)

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
    libv4l-0 \
    v4l-utils \
    # GStreamer runtime
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    python3-gi \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
 && rm -rf /var/lib/apt/lists/*

# Copy virtualenv and app sources
COPY --from=build /app/.venv /app/.venv
COPY . .

# Use venv binaries directly
ENV PATH="/app/.venv/bin:${PATH}"
# Ensure system dist-packages (python3-gi) is visible inside venv
ENV PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH}"

# Fix venv interpreter symlink path: ensure /usr/bin/python3.12 resolves
# Some uv base variants install python at /usr/local/bin/python3 only.
RUN ln -sf /usr/local/bin/python3 /usr/bin/python3.12 || true

EXPOSE 5000
VOLUME ["/app/archives"]

# Defaults for runtime
ENV OPENSENTRY_PORT=5000 \
    GUNICORN_WORKERS=1 \
    GUNICORN_TIMEOUT=60

# Ensure the uv base image ENTRYPOINT does not wrap our command
ENTRYPOINT []

# Run the app via uv (uses the pre-synced project environment; --frozen prevents resolution)
# Default to gthread worker class to avoid gevent/asyncio conflicts (overridable via env)
CMD ["sh", "-c", "uv run --frozen -m gunicorn -w ${GUNICORN_WORKERS:-1} -k ${GUNICORN_WORKER_CLASS:-gthread} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --bind 0.0.0.0:${OPENSENTRY_PORT:-5000} server:app"]

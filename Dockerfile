FROM python:3.10-slim

WORKDIR /app

# Install git and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application code
COPY app/ ./app/

# Configuration is passed at RUN time, never baked in. This image used to copy the
# local environment file in at build time, which writes the API keys into a layer:
# anyone who can pull the image can read them, and deleting the file in a later layer
# does not remove it from history. docker-compose.yml supplies the values via env_file.

# Create cache directory
RUN mkdir -p cache && chmod 755 cache

# Expose the port FastAPI runs on
EXPOSE 8000

# Cold start loads embedding models and memory-maps the vector index, which takes
# minutes on first run; the long start-period keeps the container from being killed
# and restarted while it is legitimately still warming up. /api/ready flips to true
# only when search can actually serve.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/ready || exit 1

# Command to run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

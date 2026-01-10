FROM python:3.12-slim

WORKDIR /app

# Install OS deps for SSL & networking
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Install Azure CLI
RUN pip install --no-cache-dir azure-cli

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency configuration (for layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen

# Copy application files
COPY app/ ./app/
COPY .env .

# Expose port
EXPOSE 8000

# Start FastAPI application using Uvicorn
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

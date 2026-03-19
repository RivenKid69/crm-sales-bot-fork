FROM python:3.12.12-slim

WORKDIR /app

# System deps for pymorphy3
RUN apt-get update && \
    apt-get install -y --no-install-recommends antiword build-essential catdoc curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir .

# Copy source code and config
COPY src/ src/
COPY conftest.py ./
COPY ["БД по болям/", "./БД по болям/"]

# Data directory for SQLite (conversations.db)
RUN mkdir -p /app/data

# Default env vars
ENV PYTHONUNBUFFERED=1
ENV API_KEY=change-me-in-production
ENV DB_PATH=/app/data/conversations.db

# Ollama URL override — entrypoint patches settings.yaml before start
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]

# Dockerfile - SQLDiagnose: web app + REST API in one CPU image.
#
#   docker build -f deployment/Dockerfile -t sqldiagnose .
#   docker run -p 8000:8000 -v sqldiagnose-data:/app/data/workspace sqldiagnose   # http://localhost:8000
#
# The fine-tuned classifier is copied from models/checkpoints/ if present; without it the API runs with the
# deterministic analyzer only (GET /api/v1/health reports model_loaded=false). To run queries on the example
# databases, mount their data (from `make data`) read-only, as docker-compose.yml does:
#   -v "$PWD/data/raw/spider_data/database:/app/data/raw/spider_data/database:ro"

# ---- web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- service
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

COPY analysis ./analysis
COPY configs ./configs
COPY data_pipeline ./data_pipeline
COPY deployment ./deployment
COPY evaluation ./evaluation
COPY models ./models
COPY repair ./repair
COPY services ./services
COPY training ./training
COPY utils ./utils
COPY cli.py ./
COPY data/processed/schemas.json ./data/processed/schemas.json
COPY reports ./reports
COPY --from=web /web/dist ./frontend/dist

RUN useradd --create-home app && mkdir -p data/workspace .cache/huggingface && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "deployment.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

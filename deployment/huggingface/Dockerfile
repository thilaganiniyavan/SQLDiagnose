# Dockerfile - SQLDiagnose on a Hugging Face Docker Space (https://huggingface.co/docs/hub/spaces-sdks-docker).
#
# scripts/deploy_hf.py uploads the repository with this file as the Space's root Dockerfile. Unlike
# deployment/Dockerfile it fetches the fine-tuned classifier from the GitHub release and the example databases
# from a Hugging Face dataset during the build, because neither is in git. The Space variable EXAMPLES_REPO
# (set by the deploy script) names that dataset; Spaces pass variables to the build as build arguments.

# ---- web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- service
FROM python:3.12-slim

ARG EXAMPLES_REPO=""

# Public deployment: live PostgreSQL/MySQL introspection would let visitors make the server connect to
# arbitrary hosts, so it stays off.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface \
    SQLDIAGNOSE_LIVE_SCHEMA=false

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
COPY scripts ./scripts
COPY services ./services
COPY training ./training
COPY utils ./utils
COPY cli.py ./
COPY data/processed/schemas.json ./data/processed/schemas.json
COPY reports ./reports
COPY --from=web /web/dist ./frontend/dist

RUN python scripts/download_model.py
RUN if [ -n "$EXAMPLES_REPO" ]; then \
      python -c "import sys; from huggingface_hub import snapshot_download; \
snapshot_download(repo_id=sys.argv[1], repo_type='dataset', local_dir='data/raw/spider_data/database', \
allow_patterns=['*/*.sqlite'])" "$EXAMPLES_REPO"; \
    fi

# Spaces run the container as uid 1000.
RUN useradd --create-home --uid 1000 app && mkdir -p data/workspace .cache/huggingface && chown -R app /app
USER app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "deployment.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]

# Dockerfile
# Clean Architecture: Frameworks & Drivers
# Standard Docker image utilizing multi-stage builds to limit runtime dependencies.

# Base Stage
FROM python:3.10-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency Stage
FROM base AS builder

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Final Runtime Stage
FROM python:3.10-slim AS runner

WORKDIR /app

# Copy installed site-packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project code
COPY ./configs /app/configs
COPY ./datasets /app/datasets
COPY ./models /app/models
COPY ./deployment /app/deployment
COPY ./utils /app/utils
COPY ./repair /app/repair
COPY ./evaluation /app/evaluation

# Copy fine-tuned CodeBERT model checkpoints
COPY ./experiments/exp_claudios_codebert-base_42/checkpoints /app/experiments/exp_claudios_codebert-base_42/checkpoints

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "deployment.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

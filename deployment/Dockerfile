# Dockerfile - SQLDiagnose API and UI (CPU image).
#
#   docker build -f deployment/Dockerfile -t sqldiagnose .
#   docker run -p 8000:8000 sqldiagnose                       # API
#   docker run -p 8501:8501 -e SQLDIAGNOSE_API_URL=http://host.docker.internal:8000/api/v1 \
#       sqldiagnose python -m streamlit run frontend/app.py --server.address 0.0.0.0   # UI
#
# The fine-tuned classifier is copied from models/checkpoints/ if present; without it the API
# runs with the deterministic analyzer only (GET /api/v1/health reports model_loaded=false).

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
COPY frontend ./frontend
COPY models ./models
COPY repair ./repair
COPY services ./services
COPY training ./training
COPY utils ./utils
COPY data/processed/schemas.json ./data/processed/schemas.json
COPY .streamlit ./.streamlit

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "deployment.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

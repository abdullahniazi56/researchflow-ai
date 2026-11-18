FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models

WORKDIR /app

# cpu-only torch (the default wheel pulls in CUDA)
RUN pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
    || pip install torch==2.14.0

COPY requirements.txt .
RUN pip install -r requirements.txt

# bake the models into the image
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY backend ./backend
COPY eval ./eval
COPY data/*.pdf ./data/

RUN useradd --create-home appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser /app /opt/models
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')"

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

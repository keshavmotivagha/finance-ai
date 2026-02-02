# Optimized Dockerfile for Railway Free Tier (Under 4GB)
FROM python:3.11-slim

# Environment variables for optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRANSFORMERS_CACHE=/tmp/transformers_cache \
    SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers \
    HF_HOME=/tmp/huggingface

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages - FIXED ORDER
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir spacy==3.7.5 sentence-transformers==2.7.0 transformers==4.41.2 && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm --no-deps && \
    rm -rf /root/.cache/pip/*

# Pre-download sentence transformer model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads temp_files static/uploads /tmp/transformers_cache /tmp/sentence_transformers /tmp/huggingface

# Create non-root user and set permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /tmp/transformers_cache /tmp/sentence_transformers /tmp/huggingface

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 10000

# Start with gunicorn - use shell form to expand $PORT
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --worker-class gevent --timeout 120 --access-logfile - --error-logfile -

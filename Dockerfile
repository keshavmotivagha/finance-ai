# Optimized Dockerfile for Railway Free Tier (Under 4GB)
FROM python:3.11-slim

# Critical: Multi-stage build to reduce final image size
# Environment variables for optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://download.pytorch.org/whl/cpu \
    TRANSFORMERS_CACHE=/tmp/transformers_cache \
    SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers \
    HF_HOME=/tmp/huggingface \
    PATH="/home/appuser/.local/bin:$PATH"

# Install ONLY essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoclean

# Create non-root user FIRST
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# CRITICAL: Install everything as ROOT first, then switch user
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # Install gunicorn and gevent FIRST - CRITICAL
    pip install --no-cache-dir gunicorn==22.0.0 gevent==24.2.1 && \
    # Install PyTorch CPU-only
    pip install --no-cache-dir torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu && \
    # Install other ML packages
    pip install --no-cache-dir \
        sentence-transformers==2.7.0 \
        transformers==4.41.2 \
        spacy==3.7.5 && \
    # Install remaining requirements
    grep -v "torch==" requirements.txt | \
    grep -v "sentence-transformers==" | \
    grep -v "transformers==" | \
    grep -v "spacy==" | \
    grep -v "gunicorn==" | \
    grep -v "gevent==" | \
    pip install --no-cache-dir -r /dev/stdin && \
    # Download spaCy model
    python -m spacy download en_core_web_sm --no-deps && \
    # Clean up
    rm -rf /root/.cache/pip/* && \
    find /usr/local/lib/python3.11/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type f -name "*.pyc" -delete && \
    find /usr/local/lib/python3.11/site-packages -type f -name "*.pyo" -delete && \
    find /usr/local/lib/python3.11/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Pre-download sentence transformer model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    find /tmp -type f -name "*.bin" -size +100M -delete 2>/dev/null || true

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p uploads temp_files static/uploads /tmp/transformers_cache /tmp/sentence_transformers /tmp/huggingface && \
    chmod -R 755 uploads temp_files static && \
    chown -R appuser:appuser /app /tmp/transformers_cache /tmp/sentence_transformers /tmp/huggingface

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 10000

# Use shell form to properly expand $PORT variable
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 1 \
    --threads 2 \
    --worker-class gevent \
    --worker-connections 500 \
    --worker-tmp-dir /dev/shm \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 100 \
    --max-requests-jitter 20 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload

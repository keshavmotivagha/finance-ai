FROM python:3.11-slim

# Environment variables for optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_TRIM_THRESHOLD_=100000 \
    MALLOC_MMAP_THRESHOLD_=100000 \
    TRANSFORMERS_CACHE=/tmp/transformers_cache \
    SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies and spaCy model in one layer
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# Pre-download sentence transformer model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads temp_files static/uploads /tmp/transformers_cache /tmp/sentence_transformers && \
    chmod -R 755 uploads temp_files static

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /tmp/transformers_cache /tmp/sentence_transformers

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:10000/health', timeout=5)"

# Run gunicorn
CMD gunicorn app:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 1 \
    --worker-class sync \
    --worker-tmp-dir /dev/shm \
    --timeout 300 \
    --graceful-timeout 30 \
    --max-requests 50 \
    --max-requests-jitter 10 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload

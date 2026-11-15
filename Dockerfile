# ==========================================
# Multi-Stage Dockerfile for CareCircle Platform
# Python 3.12, Minimal Footprint (<150MB), Non-Root Security
# ==========================================

# -----------------
# Stage 1: Builder
# -----------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for compiling binary packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies into target wheels directory
RUN pip install --no-cache-dir --user -r requirements.txt

# -----------------
# Stage 2: Runtime
# -----------------
FROM python:3.12-slim AS runner

WORKDIR /app

# Ensure security: run as unprivileged non-root user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 --no-create-home appuser

# Environment flags for optimal Python container execution
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:${PATH}" \
    PORT=8000

# Copy compiled dependencies from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application source code and static assets
COPY --chown=appuser:appgroup app /app/app
COPY --chown=appuser:appgroup static /app/static
COPY --chown=appuser:appgroup .env.example /app/.env.example

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

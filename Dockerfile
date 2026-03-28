FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Redis for hybrid-real, procps for process monitoring)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    redis-server \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Copy the application
COPY incident_response_env/ /app/incident_response_env/
COPY inference.py /app/inference.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create directories for runtime data
RUN mkdir -p /tmp/sre_logs

# Set Python path so imports work
ENV PYTHONPATH=/app
ENV ENABLE_WEB_INTERFACE=true

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

EXPOSE 7860

CMD ["bash", "start.sh"]

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Copy the Python package and baseline script
COPY incident_response_env/ /app/incident_response_env/
COPY baseline.py /app/baseline.py

# Set Python path so imports work
ENV PYTHONPATH=/app
ENV ENABLE_WEB_INTERFACE=true

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "incident_response_env.server.app:app", "--host", "0.0.0.0", "--port", "8000"]

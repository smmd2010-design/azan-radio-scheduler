FROM python:3.11-slim

# Needed for pychromecast/pyatv's network discovery (zeroconf/mDNS) and for
# bcrypt/cryptography wheels that occasionally need to build from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Everything persistent (settings DB, schedule, cached prayer times, logs,
# AirPlay/Alexa credentials) lives under /app/data - mount this as a volume.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8730

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8730/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8730"]

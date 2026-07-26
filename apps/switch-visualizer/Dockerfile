FROM python:3.12-slim

WORKDIR /app

# System fonts for Pillow text rendering (Segoe UI not available on Linux)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY meraki_viz/ ./meraki_viz/
COPY web/ ./web/

RUN pip install --no-cache-dir .

# Persistent VLAN color store — mount a volume here to keep colors across restarts
VOLUME ["/app/vlan_color_map.yaml"]

EXPOSE 8000

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]

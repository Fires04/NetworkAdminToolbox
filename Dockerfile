# PyFNetwork Toolbox -- one image, one process tree:
# webui/app.py (Flask) serves the cli_scripts/ UI directly and reverse-proxies
# each apps/<name>/ web app under /app/<name>/, spawning it as a child
# process on a 127.0.0.1-only internal port on first request.
FROM python:3.12-slim

WORKDIR /app

# fonts-dejavu-core: Pillow text rendering used by the switch-visualizer
# app (Segoe UI isn't available on Linux).
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Each apps/<name>/ with its own installable package needs its own pip
# install line -- see README's "Adding an app module" section.
RUN pip install --no-cache-dir -r webui/requirements.txt && \
    pip install --no-cache-dir ./apps/switch-visualizer

ENV PYTHONUNBUFFERED=1

# Only the toolbox's own port is exposed -- apps/*/app.yaml internal ports
# stay bound to 127.0.0.1 inside the container.
EXPOSE 5000

CMD ["python3", "webui/app.py"]

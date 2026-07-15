FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Invoked via `bash entrypoint.sh` rather than `./entrypoint.sh` so startup
# doesn't depend on the executable bit surviving zip/unzip or a bind mount
# from the host (the dev volume mount in docker-compose.yml replaces this
# image's /app with the host's backend/ directory at runtime, which can
# silently strip the chmod set above).
ENTRYPOINT ["bash", "entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

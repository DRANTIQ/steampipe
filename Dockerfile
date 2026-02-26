FROM python:3.11-slim

WORKDIR /app

# Steampipe from GitHub releases. TARGETARCH is set by BuildKit (arm64 on Apple Silicon, amd64 on Intel).
ARG STEAMPIPE_VERSION=v2.3.5
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates util-linux \
    && curl -sL "https://github.com/turbot/steampipe/releases/download/${STEAMPIPE_VERSION}/steampipe_linux_${TARGETARCH}.tar.gz" | tar -xz -C /usr/local/bin \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Steampipe refuses to run as root; create app user and install plugin as that user
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/sh --create-home app
ENV STEAMPIPE_CONFIG_DIR=/app/steampipe
RUN mkdir -p /app/steampipe/worker_install/config /app/steampipe/worker_install/tmp /app/steampipe/worker_install/db \
    && echo 'options "database" { port = 9194 }' > /app/steampipe/worker_install/config/default.spc \
    && chown -R app:app /app/steampipe \
    && runuser -u app -- env STEAMPIPE_INSTALL_DIR=/app/steampipe/worker_install /usr/local/bin/steampipe plugin install aws

# DB is initialized at runtime (worker sets TMPDIR to avoid cross-device link)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R app:app /app
USER app

ENV PYTHONPATH=/app
EXPOSE 8000

# .env is not copied; use --env-file .env or compose env_file when running
# Default: API. Override command for worker/scheduler.
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]

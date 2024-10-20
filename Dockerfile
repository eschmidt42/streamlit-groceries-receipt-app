FROM ubuntu:24.04@sha256:74f92a6b3589aa5cac6028719aaac83de4037bad4371ae79ba362834389035aa AS builder
RUN apt-get -y update; apt-get -y install curl
WORKDIR /work

ENV PATH=/root/.rye/shims:$PATH
RUN curl -sSf https://rye.astral.sh/get | RYE_INSTALL_OPTION="--yes" RYE_VERSION="0.41.0" bash

COPY . /work/
RUN rye build --wheel --clean --all

FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63 AS runner

# Create a non-root user
RUN useradd -m appuser

# TODO: replace with docker secrets logic, once railway supports it... https://docs.docker.com/build/building/secrets/
ENV KEY=not-set
ENV PORT=not-set

WORKDIR /app
# Copy only necessary files from builder
COPY --from=builder /work/dist/*.whl /app/
COPY --from=builder /work/app /app/app
COPY --from=builder /work/user.db /work/logger-config.json /app/
COPY --from=builder /work/.streamlit/config.toml /app/.streamlit/config.toml

# Install dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache /app/*.whl && \
    rm /app/*.whl

# Set up configuration and directories
RUN mv app/app-config-template-docker.toml app-config.toml  && \
    mkdir -p /data/og/extraction-artifacts /data/og/collation-artifacts  && \
    chown -R appuser:appuser /app /data
# RUN mv app/app-config-template-docker.toml app-config.toml
# RUN mkdir -p /data/og/extraction-artifacts /data/og/collation-artifacts
# RUN chown -R appuser:appuser /app /data

# Switch to non-root user
USER appuser

EXPOSE 8501

# Healthcheck
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run the application
CMD ["sh", "-c", "SERVICES__ANTHROPIC__KEY=${KEY} streamlit run app/main.py --server.port=${PORT} --server.address=0.0.0.0"]

FROM docker.arvancloud.ir/python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/state/home XDG_CACHE_HOME=/state/cache
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY deploy ./deploy
# Runtime resource paths follow the repository's existing editable-install contract.
RUN python -m pip install --no-cache-dir --no-deps --editable . \
    && ln -s /state/data /app/data \
    && ln -s /state/artifacts /app/artifacts \
    && ln -s /state/local /app/.local
ARG RELEASE_REVISION=uncommitted
LABEL org.opencontainers.image.revision=$RELEASE_REVISION
ENV ROYIN_RELEASE_REVISION=$RELEASE_REVISION
# The entrypoint provisions the mounted disk, then drops privileges before serving or trading.
USER 0:0
EXPOSE 3000
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "-m", "deploy.entrypoint"]

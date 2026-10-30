FROM python:3.13-slim

# Match the host user so what the app writes to the mounted data folder stays yours.
ARG UID=1000

RUN useradd --uid ${UID} --create-home --home-dir /home/app app
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

USER app
ENV HOME=/home/app UV_LINK_MODE=copy

WORKDIR /app
COPY --chown=app pyproject.toml uv.lock ./
# Every release bumps the version in these two files, so this step reruns; the cache keeps it off the network.
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=${UID} uv sync --frozen --no-dev
COPY --chown=app app ./app
COPY --chown=app plugin ./plugin

ENV DB_PATH=/data/sessions.db
EXPOSE 8765
CMD ["uv", "run", "--no-dev", "uvicorn", "--factory", "app.main:default_app", "--host", "0.0.0.0", "--port", "8765", "--timeout-graceful-shutdown", "5"]

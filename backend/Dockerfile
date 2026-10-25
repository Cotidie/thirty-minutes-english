FROM python:3.13-slim

# Match the host user so what the app writes to the mounted data folder stays yours.
ARG UID=1000

RUN useradd --uid ${UID} --create-home --home-dir /home/app app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

USER app
ENV HOME=/home/app

WORKDIR /app
COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY --chown=app app ./app
COPY --chown=app plugin ./plugin

ENV DB_PATH=/data/sessions.db
EXPOSE 8765
CMD ["uv", "run", "--no-dev", "uvicorn", "--factory", "app.main:default_app", "--host", "0.0.0.0", "--port", "8765"]

FROM python:3.13-slim

# Match the host user and home so the mounted ~/.claude/skills sits where the CLI looks.
ARG UID=1000
ARG HOME_DIR=/home/app

RUN useradd --uid ${UID} --create-home --home-dir ${HOME_DIR} app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

USER app
ENV HOME=${HOME_DIR}

WORKDIR /app
COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY --chown=app app ./app

ENV DB_PATH=/data/sessions.db
EXPOSE 8765
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]

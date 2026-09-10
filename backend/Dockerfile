FROM python:3.13-slim

# Match the host user so mounted ~/.claude/{skills,plugins} resolve at the same
# absolute paths (plugin manifests store absolute installPath values).
ARG UID=1000
ARG HOME_DIR=/home/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid ${UID} --create-home --home-dir ${HOME_DIR} app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

USER app
ENV HOME=${HOME_DIR}
ENV PATH=${HOME_DIR}/.local/bin:${PATH}
RUN curl -fsSL https://claude.ai/install.sh | bash && claude --version

WORKDIR /app
COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY --chown=app app ./app
COPY --chown=app docker-entrypoint.py ./

ENV DB_PATH=/data/sessions.db
EXPOSE 8765
ENTRYPOINT ["python3", "docker-entrypoint.py"]
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]

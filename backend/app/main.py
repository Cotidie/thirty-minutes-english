import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.generator import ClaudeCliGenerator, GenerationError, Generator
from app.models import CreateSessionRequest, Session, SessionSummary
from app.store import SessionStore
from app.topics import TOPICS, pick_topic

ROOT = Path(__file__).resolve().parent.parent
RECENT_TOPIC_WINDOW = 10


def create_app(store: SessionStore, generator: Generator) -> FastAPI:
    app = FastAPI(title="english-speaking-claude")
    app.state.store = store
    app.state.generator = generator

    @app.get("/api/topics", response_model=list[str])
    def list_topics() -> list[str]:
        return list(TOPICS)

    @app.get("/api/sessions", response_model=list[SessionSummary])
    def list_sessions(request: Request) -> list[SessionSummary]:
        return request.app.state.store.list_all()

    @app.post("/api/sessions", response_model=Session, status_code=201)
    def create_session(body: CreateSessionRequest, request: Request) -> Session:
        store: SessionStore = request.app.state.store
        topic = body.topic.strip() if body.topic and body.topic.strip() else pick_topic(
            store.recent_topics(RECENT_TOPIC_WINDOW)
        )
        try:
            content = request.app.state.generator.generate(topic)
        except GenerationError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return store.create(content)

    @app.get("/api/sessions/{session_id}", response_model=Session)
    def get_session(session_id: int, request: Request) -> Session:
        session = request.app.state.store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: int, request: Request) -> Response:
        if not request.app.state.store.delete(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return Response(status_code=204)

    return app


def default_app() -> FastAPI:
    return create_app(
        SessionStore(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db")),
        ClaudeCliGenerator(model=os.environ.get("CLAUDE_MODEL", "opus")),
    )


app = default_app()

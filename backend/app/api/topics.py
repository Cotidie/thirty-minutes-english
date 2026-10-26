from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Svc, Topics
from app.db.topics import TopicInUse
from app.models import TopicLibrary, TopicListing

router = APIRouter(prefix="/api/topics")


@router.get("", response_model=TopicListing)
def list_topics(topics: Topics, services: Svc) -> TopicListing:
    topics.ensure_fetched(services.topic_source)
    return topics.listing()


@router.post("/refresh", response_model=TopicListing)
def refresh_topics(topics: Topics, services: Svc) -> TopicListing:
    topics.refresh(services.topic_source)
    return topics.listing()


@router.get("/all", response_model=TopicLibrary)
def list_every_topic(db: Db) -> TopicLibrary:
    """Every topic with the days it led the news and the sessions written on it, for the database page."""
    return TopicLibrary(topics=db.topics.list_all())


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: int, db: Db) -> Response:
    """The topic, out of the pool and the days that listed it; a topic a session was written on stays."""
    try:
        deleted = db.topics.delete(topic_id)
    except TopicInUse:
        raise HTTPException(status_code=409, detail="a session uses this topic") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="topic not found")
    return Response(status_code=204)

from fastapi import APIRouter

from app.api.deps import Db, Svc, Topics
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

from fastapi import APIRouter

from app.api.deps import Svc, Topics
from app.models import TopicListing

router = APIRouter(prefix="/api/topics")


@router.get("", response_model=TopicListing)
def list_topics(topics: Topics, services: Svc) -> TopicListing:
    topics.ensure_fetched(services.topic_source)
    return topics.listing()


@router.post("/refresh", response_model=TopicListing)
def refresh_topics(topics: Topics, services: Svc) -> TopicListing:
    topics.refresh(services.topic_source)
    return topics.listing()

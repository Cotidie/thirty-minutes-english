from fastapi import APIRouter

from app.api.deps import Db
from app.models import CorpusEntry

router = APIRouter(prefix="/api")


@router.get("/expressions", response_model=list[CorpusEntry])
def list_expressions(db: Db) -> list[CorpusEntry]:
    """The whole corpus; the page searches and filters it in the browser."""
    return db.expressions.list_all()

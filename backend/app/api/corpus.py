from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import Db, admin_only
from app.models import CorpusEntry

router = APIRouter(prefix="/api", dependencies=[Depends(admin_only)])


@router.get("/expressions", response_model=list[CorpusEntry])
def list_expressions(db: Db) -> list[CorpusEntry]:
    """The whole corpus; the page searches and filters it in the browser."""
    return db.expressions.list_all()


@router.delete("/expressions/{expression_id}", status_code=204)
def delete_expression(expression_id: int, db: Db) -> Response:
    """The expression, out of the corpus and out of every session that taught it."""
    if not db.expressions.delete(expression_id):
        raise HTTPException(status_code=404, detail="expression not found")
    return Response(status_code=204)

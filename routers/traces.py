from fastapi import APIRouter, Depends, HTTPException
from routers.issues import info
from utils.dependencies import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, func
from typing import List
import models, schemas
from datetime import datetime

router = APIRouter(prefix="/traces", tags=["Traces"])


@router.get("/{trace_id}", response_model=schemas.TraceFull)
async def info(
    trace_id: int,
    db: Session = Depends(get_db)):

    trace = db.query(models.Trace).filter(models.Trace.id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace

    

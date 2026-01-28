from fastapi import APIRouter, Depends, HTTPException
from utils.dependencies import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, func
from typing import List
import models, schemas
from datetime import datetime

router = APIRouter(prefix="/issues", tags=["Issues"])

@router.get("", response_model=List[schemas.IssuePreview])
async def list(db: Session = Depends(get_db)):
    
    issues_data = db.query(
        models.Issue,
        func.max(models.Trace.occurrence).label('last_occurrence')
    ).join(
        models.Trace,
        models.Issue.id == models.Trace.issue_id
    ).group_by(
        models.Issue.id, 
        models.Issue.name,
        models.Issue.type
    ).order_by(
        desc(func.max(models.Trace.occurrence)) 
    ).all()
    
    issues_list = []
    for issue, last_occurrence in issues_data:
        issue.last_occurrence = last_occurrence
    
        issues_list.append(issue)
    
    return issues_list    
    


@router.get("/{issue_id}", response_model=schemas.IssueFull)
async def info(
    issue_id: int,
    db: Session = Depends(get_db),):
    
    issue = db.query(models.Issue).filter(models.Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    traces = db.query(
        models.Trace.id,
        models.Trace.device_id,
        models.Trace.issue_id,
        models.Trace.occurrence
    ).filter(
        models.Trace.issue_id == issue_id
    ).order_by(
        desc(models.Trace.occurrence)
    ).all()
    
    
    return schemas.IssueFull(
        id=issue.id,
        name=issue.name,
        type=issue.type,
        traces=traces
    )

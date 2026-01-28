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
        models.IssueDevice.c.occurrence
    ).join(
        models.IssueDevice,
        models.Issue.id == models.IssueDevice.c.issue_id
    ).all()
    
    issues_list = []
    for issue, occurrence in issues_data:
        issues_list.append({
            "id": issue.id,
            "name": issue.name,
            "type": issue.type,
            "occurrence": occurrence, 
        })
    
    return issues_list



@router.get("/{issue_id}", response_model=schemas.IssueFull)
async def get_issue_with_traces(
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

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from utils.dependencies import get_db

router = APIRouter(prefix="/projects", tags=["Projects (Device Types)"])

@router.post("", response_model=schemas.DeviceTypeOut)
def create_project(project: schemas.DeviceTypeCreate, db: Session = Depends(get_db)):
    existing = db.query(models.DeviceType).filter(models.DeviceType.name == project.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project with this name already exists")
    
    db_project = models.DeviceType(**project.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("", response_model=list[schemas.DeviceTypeOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.DeviceType).all()

@router.get("/{project_id}", response_model=schemas.DeviceTypeOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.DeviceType).filter(models.DeviceType.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.DeviceType).filter(models.DeviceType.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.devices:
        raise HTTPException(status_code=400, detail="Cannot delete project with active devices")
        
    db.delete(project)
    db.commit()
    return {"status": "success"}


@router.get("/{project_id}/devices", response_model=List[schemas.DeviceOut])
def get_project_devices(project_id: int, db: Session = Depends(get_db)):
    devices = db.query(models.Device).join(models.Group).filter(models.Group.project_id == project_id).all()
    return devices


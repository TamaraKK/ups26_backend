from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from utils.dependencies import get_db

router = APIRouter(prefix="/metadata", tags=["Metadata"])

@router.get("", response_model=List[schemas.MetricMetadataOut])
def list_metadata(db: Session = Depends(get_db)):
    """Получить список всех метрик с их порогами и описаниями"""
    return db.query(models.MetricMetadata).all()

@router.patch("/{meta_id}", response_model=schemas.MetricMetadataOut)
def update_metadata(
    meta_id: int, 
    meta_update: schemas.MetricMetadataBase, # Используем базу, чтобы все поля были Optional
    db: Session = Depends(get_db)
):
    """Обновить пороги или описания метрики"""
    db_meta = db.query(models.MetricMetadata).filter(models.MetricMetadata.id == meta_id).first()
    if not db_meta:
        raise HTTPException(status_code=404, detail="Metadata not found")
    
    # Модифицируем только присланные поля
    update_data = meta_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_meta, key, value)
    
    db.commit()
    db.refresh(db_meta)
    return db_meta

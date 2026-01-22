from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session 
import models
import schemas
from utils.dependencies import get_db

router = APIRouter(prefix="/metadata", tags=["Metadata (Metrics)"])

@router.get("/metrics", response_model=List[schemas.MetricMetadataOut])
def get_metrics_metadata(db: Session = Depends(get_db)):
    """
    Отдает фронтенду 'словарь' (имя метрики -> иконка и перевод).
    Доступен по адресу: GET /metadata/metrics
    """
    return db.query(models.MetricMetadata).all()

from fastapi import APIRouter, Depends, HTTPException
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional

from utils.dependencies import get_db
import models
import schemas
from model.model import model_prediction_report 

router = APIRouter(prefix="/predictive-alerts", tags=["Predictive Analytics"])

import asyncio
from datetime import datetime, timezone

async def run_predictive_background_task(db_factory):
    target_metrics = ["device_cpu_usage", "device_battery_level", "device_dryer_temp_now"]
    
    while True:
        db = db_factory()
        try:
            devices = db.query(models.Device).all()
            
            for device in devices:
                for metric in target_metrics:
                    metrics_query = db.query(models.DeviceTelemetry).filter(
                        models.DeviceTelemetry.device_id == device.id,
                        models.DeviceTelemetry.metric_name == metric
                    ).order_by(models.DeviceTelemetry.created_at.desc()).limit(150).all()

                    if len(metrics_query) < 60:
                        continue 

                    data = [m.value for m in metrics_query]
                    series = pd.Series(data[::-1])
                    report = model_prediction_report(series)

                    if report["status"] in ["warning", "critical"]:
                        new_alert = models.PredictiveAlert(
                            device_id=device.id,
                            metric_name=metric, 
                            status=report["status"],
                            minutes_to_failure=report["minutes_until_failure"],
                            forecast_max=report["forecast_max"]
                        )
                        db.add(new_alert)
                        db.commit()
                        print(f"alert saved for device {device.serial}: {report['status']}")
                    else:
                        pass
            db.commit()
            print(f"[{datetime.now()}] Аналитика по всем устройствам успешно сохранена.")
            
        except Exception as e:
            print(f"Ошибка в фоновом анализе: {e}")
            db.rollback()
        finally:
            db.close()
        
        await asyncio.sleep(30)


@router.get("/history/{device_id}", response_model=List[schemas.PredictiveAlertOut])
def get_alerts_history(
    device_id: int, 
    metric: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    query = db.query(models.PredictiveAlert).filter(
        models.PredictiveAlert.device_id == device_id
    )
    
    if metric:
        query = query.filter(models.PredictiveAlert.metric_name == metric)
        
    return query.order_by(models.PredictiveAlert.created_at.desc()).limit(20).all()



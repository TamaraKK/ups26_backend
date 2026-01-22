from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas, httpx
from utils.dependencies import get_db

router = APIRouter(prefix="/devices", tags=["Devices"])

PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

@router.post("/", response_model=schemas.DeviceOut)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    type_exists = db.query(models.DeviceType).filter(models.DeviceType.id == device.type_id).first()
    if not type_exists:
        raise HTTPException(status_code=404, detail="Device Type not found")

    if device.group_id:
        group_exists = db.query(models.Group).filter(models.Group.id == device.group_id).first()
        if not group_exists:
            raise HTTPException(status_code=404, detail="Group not found")
            
    db_device = models.Device(**device.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

@router.patch("/{device_id}", response_model=schemas.DeviceOut)
def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    update_data = device_update.model_dump(exclude_unset=True)

    if "location" in update_data and isinstance(update_data["location"], list):
        lat, lon = update_data["location"]
        update_data["location"] = f"({lat},{lon})"
    
    for key, value in update_data.items():
        setattr(db_device, key, value)
    
    db.commit()
    db.refresh(db_device)
    return db_device

@router.get("/stats", response_model=schemas.DeviceStats)
async def get_device_stats(db: Session = Depends(get_db)):
    # 1. Считаем общее кол-во в базе
    total_count = db.query(models.Device).count()
    
    # 2. Опрашиваем Prometheus на наличие активных серийников
    online_count = 0
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(PROMETHEUS_URL, params={
                "query": "device_runtime_status == 1"
            })
            data = response.json()
            # Кол-во результатов в списке и есть кол-во онлайн устройств
            online_count = len(data.get("data", {}).get("result", []))
    except Exception as e:
        print(f"Prometheus query error: {e}")
            
    return {
        "total": total_count,
        "online": online_count,
        "offline": max(0, total_count - online_count)
    }

@router.get("/{device_id}", response_model=schemas.DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    return db_device

@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(db_device)
    db.commit()
    return {"status": "success", "message": "Device deleted"}



# массив с мапами name, on, problematic (status) метрики, выходящие за грань, off. по группам и все
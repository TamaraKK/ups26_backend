from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import models, schemas, httpx
from utils.dependencies import get_db

router = APIRouter(prefix="/devices", tags=["Devices"])

PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

async def get_online_serials() -> set:
    """Вспомогательная функция: получает набор всех серийников, которые сейчас Online"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(PROMETHEUS_URL, params={"query": "device_runtime_status == 1"})
            results = resp.json().get("data", {}).get("result", [])
            return {r["metric"]["serial"] for r in results}
    except Exception as e:
        print(f"Prometheus connection error: {e}")
        return set()

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
    # По умолчанию новый девайс онлайн
    db_device.is_online = True
    return db_device

@router.get("/", response_model=List[schemas.DeviceOut])
async def list_devices(db: Session = Depends(get_db)):
    db_devices = db.query(models.Device).all()
    online_serials = await get_online_serials()
    
    for dev in db_devices:
        dev.is_online = dev.serial in online_serials
        
    return db_devices

@router.get("/stats", response_model=schemas.DeviceStats)
async def get_device_stats(db: Session = Depends(get_db)):
    total_count = db.query(models.Device).count()
    online_serials = await get_online_serials()
    online_count = len(online_serials)
            
    return {
        "total": total_count,
        "online": online_count,
        "offline": max(0, total_count - online_count)
    }

@router.get("/{device_id}", response_model=schemas.DeviceOut)
async def get_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    online_serials = await get_online_serials()
    db_device.is_online = db_device.serial in online_serials
    return db_device

@router.patch("/{device_id}", response_model=schemas.DeviceOut)
async def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db)):
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
    
    # Обновляем статус после патча для корректного ответа
    online_serials = await get_online_serials()
    db_device.is_online = db_device.serial in online_serials
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
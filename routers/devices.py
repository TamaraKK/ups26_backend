from datetime import datetime, timezone
import time
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
            # resp = await client.get(PROMETHEUS_URL, params={"query": "device_runtime_status == 1"})
            query = 'device_runtime_status == 1 and (time() - push_time_seconds < 300)'
            resp = await client.get(PROMETHEUS_URL, params={"query": query})
            results = resp.json().get("data", {}).get("result", [])
            return {r["metric"]["serial"] for r in results}
    except Exception as e:
        print(f"Prometheus connection error: {e}")
        return set()

@router.post("", response_model=schemas.DeviceOut)
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

@router.get("", response_model=List[schemas.DeviceOut])
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


@router.get("/{serial}/metrics/{metric_name}/history", response_model=schemas.MetricHistoryOut)
async def get_metric_history(
    serial: str, 
    metric_name: str, 
    hours: int = Query(3, ge=1, le=24),
    db: Session = Depends(get_db)
):
    # 1. Ищем метаданные в базе (красивое имя и единицы измерения)
    meta = db.query(models.MetricMetadata).filter(
        models.MetricMetadata.metric_name == metric_name
    ).first()

    # 2. Запрос в Prometheus за цифрами
    end_time = int(time.time())
    start_time = end_time - (hours * 3600)
    full_name = f"device_{metric_name.replace('.', '_')}"
    
    params = {
        "query": f'{full_name}{{source="{serial}"}}',
        "start": start_time,
        "end": end_time,
        "step": "60s"
    }

    async with httpx.AsyncClient() as client:
        try:
            # Тут используем URL прометея /query_range
            resp = await client.get("http://prometheus:9090/api/v1/query_range", params=params)
            data = resp.json()
            
            history = []
            if data.get("data", {}).get("result"):
                # Парсим хитрый формат Прометея [[ts, val], [ts, val]...]
                for val in data["data"]["result"][0]["values"]:
                    history.append({
                        "time": int(val[0]),
                        "value": float(val[1])
                    })

            return {
                "metric_name": metric_name,
                "display_name": meta.display_name_ru if meta else metric_name,
                "unit": meta.unit if meta else "",
                "history": history
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Prometheus error: {e}")




@router.get("/{serial}/full-report", response_model=schemas.DeviceFullDetailOut)
async def get_device_full_report(
    serial: str, 
    db: Session = Depends(get_db),
    hours: int = Query(3, ge=1)
):
    # 1. Получаем инфо из БД
    db_device = db.query(models.Device).filter(models.Device.serial == serial).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Считаем статус онлайн прямо здесь
    online_serials = await get_online_serials()
    db_device.is_online = serial in online_serials

    # 2. Получаем Метрики (температура, влажность и т.д.)
    # Здесь можно сделать цикл по всем метрикам, привязанным к типу устройства
    # Для примера возьмем 'temp' и 'humidity'
    metric_names = ["temp", "humidity"] 
    metrics_data = []
    for m_name in metric_names:
        # Используем твою логику из get_metric_history
        hist = await get_metric_history(serial, m_name, hours, db)
        metrics_data.append(hist)

    # 3. Получаем Логи из Loki
    logs_data = await get_device_logs(serial, limit=50, hours=hours)

    return {
        "device_info": db_device,
        "metrics": metrics_data,
        "logs": logs_data["logs"]
    }


# URL для запросов в Loki (Query)
LOKI_QUERY_URL = "http://loki:3100/loki/api/v1/query_range"

@router.get("/{serial}/logs", response_model=schemas.DeviceLogsResponse)
async def get_device_logs(
    serial: str, 
    limit: int = Query(50, ge=1, le=1000), # Сколько строк вернуть
    hours: int = Query(24, ge=1)           # За какой период
):
    """Получение логов устройства из Loki"""
    end_time = int(time.time() * 10**9) # Loki любит наносекунды
    start_time = end_time - (hours * 3600 * 10**9)

    # Формируем LogQL запрос: ищем по лейблу source (который мы слали в main.py)
    params = {
        "query": f'{{source="{serial}"}}',
        "limit": limit,
        "start": start_time,
        "end": end_time,
        "direction": "backward" # Сначала новые
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(LOKI_QUERY_URL, params=params)
            data = resp.json()
            
            output_logs = []
            
            # Парсим структуру ответа Loki
            for stream in data.get("data", {}).get("result", []):
                # Извлекаем уровень лога из лейблов, если он там есть
                level = stream.get("stream", {}).get("level", "INFO")
                
                for val in stream.get("values", []):
                    # val[0] - это наносекунды, val[1] - текст сообщения
                    ts_ns = int(val[0])
                    # Конвертируем в читаемое время (ISO)
                    ts_iso = datetime.fromtimestamp(ts_ns / 10**9, tz=timezone.utc).isoformat()
                    
                    output_logs.append({
                        "timestamp": ts_iso,
                        "level": level,
                        "message": val[1]
                    })

            # Сортируем по времени (на случай если было несколько стримов)
            output_logs.sort(key=lambda x: x["timestamp"], reverse=True)

            return {
                "serial": serial,
                "logs": output_logs
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loki connection error: {e}")

from datetime import datetime, timezone
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import desc, select, func
from typing import List
from routers.projects import get_all_active_alerts
import models, schemas, httpx
from utils.dependencies import get_db
from schemas import DeviceStatusEnum

router = APIRouter(prefix="/devices", tags=["Devices"])

PROMETHEUS_ALERTS_URL = "http://prometheus:9090/api/v1/alerts"
PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

# async def get_online_serials() -> set:
#     try:
#         async with httpx.AsyncClient() as client:
#             query = 'device_runtime_status'
#             resp = await client.get(PROMETHEUS_URL, params={"query": query}, timeout=3.0)
            
#             if resp.status_code != 200:
#                 return set()

#             data = resp.json()
#             results = data.get("data", {}).get("result", [])
            
#             online_serials = set()
#             for r in results:
#                 metric_labels = r.get("metric", {})
#                 s = metric_labels.get("serial")
#                 if not s:
#                     continue
                
#                 value_list = r.get("value", [])
#                 if len(value_list) > 1 and str(value_list[1]) == "1":
#                     online_serials.add(s)
            
#             print(f"DEBUG: Found online serials: {online_serials}") # Проверим, что находит
#             return online_serials
            
#     except Exception as e:
#         print(f"DEBUG: get_online_serials error: {e}")
#         return set()

async def get_online_serials() -> set:
    
    query = 'changes(device_cpu_usage[30s]) > 0'
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                PROMETHEUS_URL,
                params={"query": query},
                timeout=3.0
            )
            
            if resp.status_code != 200:
                return set()

            data = resp.json()
            results = data.get("data", {}).get("result", [])
            
            online_serials = {
                r["metric"]["serial"] 
                for r in results 
                if "serial" in r.get("metric", {})
            }
            
            return online_serials
    except Exception as e:
        print(f"Request failed: {e}")
        return set()
    
@router.post("", response_model=schemas.DeviceOut)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    if device.group_id:
        group_exists = db.query(models.Group).filter(models.Group.id == device.group_id).first()
        if not group_exists:
            raise HTTPException(status_code=404, detail="Group not found")
            
    db_device = models.Device(**device.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    db_device.status = DeviceStatusEnum.OFFLINE
    return db_device

@router.get("", response_model=List[schemas.DeviceOut])
async def list_devices(db: Session = Depends(get_db)):
    db_devices = db.query(models.Device).all()

    online_serials = await get_online_serials()

    for dev in db_devices:
        if dev.serial in online_serials:
            dev.status = schemas.DeviceStatusEnum.ONLINE
        else:
            dev.status = schemas.DeviceStatusEnum.OFFLINE
        
    return db_devices

@router.get("/{device_id}", response_model=schemas.DeviceOut)
async def get_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    online_serials = await get_online_serials()
    if db_device.serial in online_serials:
            db_device.status = schemas.DeviceStatusEnum.ONLINE
    else:
        db_device.status = schemas.DeviceStatusEnum.OFFLINE
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
    
    online_serials = await get_online_serials()
    if db_device.serial in online_serials:
            db_device.status = schemas.DeviceStatusEnum.ONLINE
    else:
        db_device.status = schemas.DeviceStatusEnum.OFFLINE
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
    meta = db.query(models.MetricMetadata).filter(
        models.MetricMetadata.metric_name == metric_name
    ).first()

    # 2. Запрос в Prometheus за цифрами
    end_time = int(time.time())
    start_time = end_time - (hours * 3600)
    full_name = f"device_{metric_name.replace('.', '_')}"
    
    params = {
        "query": f'{full_name}{{serial="{serial}"}}',
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



@router.get("/{device_id}/full-report", response_model=schemas.DeviceFullDetailOut)
async def get_device_full_report(
    device_id: int, 
    db: Session = Depends(get_db),
    hours: int = Query(3, ge=1)
):
    # 1. Сначала получаем девайс
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    serial = db_device.serial
    current_status = DeviceStatusEnum.OFFLINE
    online_serials = await get_online_serials()

    if serial in online_serials:

        current_status = DeviceStatusEnum.ONLINE
        
        all_active_alerts = await get_all_active_alerts(db)
        device_has_alerts = any(alert['serial'] == serial for alert in all_active_alerts)
        
        if device_has_alerts:
             current_status = DeviceStatusEnum.PROBLEMATIC

    end_time = int(time.time())
    start_time = end_time - (hours * 3600)
    
    metrics_data = []
    all_meta = {m.metric_name: m for m in db.query(models.MetricMetadata).all()}

    async with httpx.AsyncClient() as client:
        
        try:
            metrics_query = f'{{serial="{serial}"}}'
            list_resp = await client.get(
                "http://prometheus:9090/api/v1/query", 
                params={"query": metrics_query, "time": end_time},
                timeout=5.0
            )
            
            if list_resp.status_code == 200:
                available_metrics = list_resp.json().get("data", {}).get("result", [])
                
                for metric in available_metrics:
                    labels = metric.get("metric", {})
                    full_name = labels.get("__name__", "")
                    
                    if not full_name.startswith("device_"):
                        continue
                        
                    short_name = full_name.replace("device_", "")
                    
                    # История конкретной метрики
                    history_params = {
                        "query": f'{full_name}{{serial="{serial}"}}',
                        "start": start_time,
                        "end": end_time,
                        "step": "60s"
                    }
                    
                    history_resp = await client.get("http://prometheus:9090/api/v1/query_range", params=history_params)
                    if history_resp.status_code == 200:
                        history_result = history_resp.json().get("data", {}).get("result", [])
                        
                        if not history_result:
                            continue
                        
                        history = [{"time": int(v[0]), "value": float(v[1])} for v in history_result[0].get("values", [])]
                        
                        meta = all_meta.get(short_name)
                        metric_status = "normal"
                        
                        if history and meta:
                            last_val = history[-1]["value"]
                            if (meta.max_threshold and last_val > meta.max_threshold) or \
                               (meta.min_threshold and last_val < meta.min_threshold):
                                metric_status = "problematic"
                        
                        metrics_data.append({
                            "metric_name": short_name,
                            "display_name": meta.display_name_ru if meta else short_name,
                            "unit": meta.unit if meta else "",
                            "status": metric_status,
                            "history": history
                        })
        except Exception as e:
            print(f"Prometheus Bulk Error for serial {serial}: {e}")

        # 3. ЛОГИ (Loki)
        logs_data = []
        try:
            end_time_ns = int(time.time() * 10**9)
            start_time_ns = end_time_ns - (hours * 3600 * 10**9)
            
            logs_params = {
                "query": f'{{serial="{serial}"}}', # Ищем по serial
                "limit": 50,
                "start": start_time_ns,
                "end": end_time_ns,
                "direction": "backward"
            }
            
            logs_resp = await client.get("http://loki:3100/loki/api/v1/query_range", params=logs_params, timeout=5.0)
            if logs_resp.status_code == 200:
                logs_result = logs_resp.json().get("data", {}).get("result", [])
                
                for stream in logs_result:
                    level = stream.get("stream", {}).get("level", "INFO")
                    for value in stream.get("values", []):
                        ts_ns = int(value[0])
                        ts_iso = datetime.fromtimestamp(ts_ns / 10**9, tz=timezone.utc).isoformat()
                        logs_data.append({
                            "timestamp": ts_iso,
                            "level": level,
                            "message": value[1]
                        })
                
                logs_data.sort(key=lambda x: x["timestamp"], reverse=True)
            else:
                print(f"Loki returned error {logs_resp.status_code}: {logs_resp.text}")
        except Exception as e:
            print(f"Loki connection error for serial {serial}: {e}")

    issues_data = db.query(
            models.Issue,
            func.max(models.Trace.occurrence).label('last_occurrence'),
            func.count(models.Trace.id).label('total_trace_count'),
            func.count(func.distinct(models.Trace.device_id)).label('unique_device_count')
        ).join(
            models.Trace,
            models.Issue.id == models.Trace.issue_id
        ).group_by(
            models.Issue.id, 
            models.Issue.name,
            models.Issue.type
        ).order_by(
            desc(func.max(models.Trace.occurrence)) 
        ).filter(
            models.Trace.device_id == device_id
        ).all()
    
    issues_list = []
    for issue, last_occurrence, total_trace_count, unique_device_count in issues_data:
        issue.last_occurrence = last_occurrence
        issue.device_count = unique_device_count
        
        issues_list.append(issue)
    
    return {
        "device_info": {
             **db_device.__dict__,
             "status": current_status, 
        },
        "metrics": metrics_data,
        "logs": logs_data[:50],
        "issues": issues_list,}

# URL для запросов в Loki (Query)
LOKI_QUERY_URL = "http://loki:3100/loki/api/v1/query_range"

@router.get("/{device_id}/logs", response_model=schemas.DeviceLogsResponse)
async def get_device_logs(
    device_id: int,  
    limit: int = 50,              
    hours: int = 24,   
    db: Session = Depends(get_db) 
):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    serial = db_device.serial
    
    end_time = int(time.time() * 10**9)
    start_time = end_time - (hours * 3600 * 10**9)

    params = {
        "query": f'{{serial="{serial}"}}',
        "limit": limit,
        "direction": "backward"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(LOKI_QUERY_URL, params=params)
            data = resp.json()
            
            output_logs = []
            
            for stream in data.get("data", {}).get("result", []):
                level = stream.get("stream", {}).get("level", "INFO")
                
                for val in stream.get("values", []):
                    ts_ns = int(val[0]) 
                    message = val[1] 
                    
                    ts_iso = datetime.fromtimestamp(ts_ns / 10**9, tz=timezone.utc).isoformat()
                    
                    output_logs.append({
                        "timestamp": ts_iso,
                        "level": level,
                        "message": message
                    })

            output_logs.sort(key=lambda x: x["timestamp"], reverse=True)

            return {
                "serial": serial, # Оставляем для инфы в схеме
                "logs": output_logs
            }
    except Exception as e:
        print(f"Loki connection error: {e}")
        return {"serial": serial, "logs": []}

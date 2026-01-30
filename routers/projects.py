from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from utils.dependencies import get_db
from sqlalchemy import desc, select, func
import httpx

router = APIRouter(prefix="/projects", tags=["Projects"])
PROMETHEUS_ALERTS_URL = "http://prometheus:9090/api/v1/alerts"
PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

@router.get("/alerts", response_model=List[schemas.AlertWithMetadata])
async def get_all_active_alerts(db: Session = Depends(get_db)):
    # 1. Запрос в Prometheus за активными алертами
    prometheus_alerts = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://prometheus:9090/api/v1/alerts")
            prometheus_alerts = resp.json().get("data", {}).get("alerts", [])
    except Exception as e:
        print(f"Prometheus Alerts Error: {e}")
        return []

    # 2. Берем устройства для маппинга
    devices = db.query(models.Device).all()
    device_map = {
        d.serial: {
            "group": d.group.name if d.group else "Без группы",
            # "alias": d.alias or d.serial
        } for d in devices
    }

    # 3. Собираем плоский список с метаданными
    enriched_alerts = []
    
    for alert in prometheus_alerts:
        if alert["state"] != "firing":
            continue
            
        # Пытаемся достать серийник из лейблов
        serial = alert["labels"].get("serial") or alert["labels"].get("instance")
        
        # Данные из БД (если нашли)
        meta = device_map.get(serial)

        enriched_alerts.append({
            "alertname": alert["labels"].get("alertname"),
            "severity": alert["labels"].get("severity", "warning"),
            "summary": alert["annotations"].get("summary", ""),
            "description": alert["annotations"].get("description", ""),
            "active_at": alert.get("activeAt"),
            "serial": serial or "unknown",
            # "device_alias": meta["alias"],
            # "group_name": meta["group"]
        })

    return enriched_alerts


@router.get("/projects/{project_id}/groups", response_model=List[schemas.GroupOut])
async def get_project_groups(project_id: int, db: Session = Depends(get_db)):
    """Получить список всех групп проекта"""
    groups = db.query(models.Group).filter(models.Group.project_id == project_id).all()
    if not groups:
        return []
    return groups


@router.post("", response_model=schemas.ProjectOut)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Project).filter(models.Project.name == project.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project with this name already exists")
    
    db_project = models.Project(**project.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("", response_model=List[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).all()

@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    has_devices = db.query(models.Device).join(models.Group).filter(models.Group.project_id == project_id).first()
    if has_devices:
        raise HTTPException(status_code=400, detail="Cannot delete project with active devices")
        
    db.delete(project)
    db.commit()
    return {"status": "success"}

@router.get("/{project_id}/dashboard", response_model=schemas.ProjectDashboardOut)
async def get_project_dashboard(project_id: int, db: Session = Depends(get_db)):
    online_serials = set()
    try:
        # Проверяем тех, кто пушил в последние 5 минут
        query = 'device_runtime_status == 1 and (time() - push_time_seconds < 300)'
        async with httpx.AsyncClient() as client:
            resp = await client.get(PROMETHEUS_URL, params={"query": query})
            results = resp.json().get("data", {}).get("result", [])
            online_serials = {r["metric"]["serial"] for r in results}
    except Exception as e:
        print(f"Prometheus error: {e}")

    project_groups = db.query(models.Group).filter(models.Group.project_id == project_id).all()
    
    groups_stat = []
    total_on = 0
    total_off = 0

    for group in project_groups:
        on, off = 0, 0
        # Теперь все устройства в этой группе по умолчанию относятся к этому проекту
        for dev in group.devices:
            if dev.serial in online_serials:
                on += 1
                total_on += 1
            else:
                off += 1
                total_off += 1
        
        groups_stat.append({
            "name": group.name,
            "online": on,
            "offline": off
        })

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
    ).all()
    
    issues_list = []
    for issue, last_occurrence, total_trace_count, unique_device_count in issues_data:
        issue.last_occurrence = last_occurrence
        issue.device_count = unique_device_count
    
        issues_list.append(issue)

    return {
        "groups_stat": groups_stat,
        "total_stat": {
            "total": total_on + total_off,
            "online": total_on,
            "offline": total_off
        },
        "issues": issues_list
    }


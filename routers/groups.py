from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from utils.dependencies import get_db
import httpx

router = APIRouter(prefix="/groups", tags=["Groups"])

@router.post("/", response_model=schemas.GroupOut)
def create_group(group: schemas.GroupCreate, db: Session = Depends(get_db)):
    db_group = models.Group(**group.model_dump())
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

@router.get("/", response_model=List[schemas.GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(models.Group).all()

@router.get("/{group_id}", response_model=schemas.GroupDetail)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    db_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    db.query(models.Device).filter(models.Device.group_id == group_id).update({"group_id": None})
    
    db.delete(db_group)
    db.commit()
    
    return {"status": "success", "message": f"Group {group_id} deleted, devices unlinked"}


PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

@router.get("/dashboard/{project_id}", response_model=schemas.ProjectDashboardOut)
async def get_project_dashboard(project_id: int, db: Session = Depends(get_db)):
    # 1. Получаем живые серийники из Prometheus
    online_serials = set()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(PROMETHEUS_URL, params={"query": "device_runtime_status == 1"})
            results = resp.json().get("data", {}).get("result", [])
            online_serials = {r["metric"]["serial"] for r in results}
    except Exception as e:
        print(f"Prometheus connection error: {e}")

    groups = db.query(models.Group).all()
    
    groups_stat = []
    total_on = 0
    total_off = 0

    for group in groups:
        project_devices = [d for d in group.devices if d.type_id == project_id]
        
        if not project_devices:
            continue # Пропускаем группу, если в ней нет девайсов этого проекта

        on, off = 0, 0
        for dev in project_devices:
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

    return {
        "groups_stat": groups_stat,
        "total_stat": {
            "total": total_on + total_off,
            "online": total_on,
            "offline": total_off
        }
    }


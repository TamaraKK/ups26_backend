from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from routers.devices import get_online_serials
import models, schemas
from utils.dependencies import get_db
# import httpx

router = APIRouter(prefix="/groups", tags=["Groups"])

@router.post("", response_model=schemas.GroupOut)
def create_group(group: schemas.GroupCreate, db: Session = Depends(get_db)):
    db_group = models.Group(**group.model_dump())
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

@router.get("", response_model=List[schemas.GroupDetail])
async def list_groups(db: Session = Depends(get_db)):
    groups = db.query(models.Group).all()
    
    online_serials = await get_online_serials()
    
    for group in groups:
        for device in group.devices:
            if device.serial in online_serials:
                device.status = schemas.DeviceStatusEnum.ONLINE
            else:
                device.status = schemas.DeviceStatusEnum.OFFLINE
    
    return groups

@router.get("/{group_id}", response_model=schemas.GroupDetail)
async def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    online_serials = await get_online_serials()

    for device in group.devices:
        if device.serial in online_serials:
            device.status = schemas.DeviceStatusEnum.ONLINE
        else:
            device.status = schemas.DeviceStatusEnum.OFFLINE
    
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





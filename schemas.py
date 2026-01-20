from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class GroupTypeEnum(str, Enum):
    geo = 'geolocation'
    type = 'type'
    status = 'status'

#=---group schemas-----------------
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: GroupTypeEnum

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[GroupTypeEnum] = None

class GroupOut(BaseModel):
    id: int
    name: str
    type: GroupTypeEnum
    # devices_count: int =  0
    model_config = {"from_attributes": True}

class GroupDetail(GroupOut):
    devices: List["DeviceOut"] = []

# --- device schemas--------------
class DeviceCreate(BaseModel):
    serial: str = Field(..., min_length=1, max_length=50)
    type: str = Field(..., min_length=1, max_length=50)
    group_id: Optional[int] = None

class DeviceUpdate(BaseModel):
    serial: Optional[str] = Field(None, min_length=1, max_length=50)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    group_id: Optional[int] = Field(None, ge=1)

class DeviceOut(BaseModel):
    id: int
    serial: str
    type: str
    group_id: Optional[int]
    group: Optional[GroupOut] = None
    model_config = {"from_attributes": True}



GroupDetail.model_rebuild()
















# ========== Statistics ==========
# class GroupStats(BaseModel):
#     total_groups: int
#     groups_by_type: dict

# class DeviceStats(BaseModel):
#     total_devices: int
#     devices_without_group: int
#     devices_by_group: dict


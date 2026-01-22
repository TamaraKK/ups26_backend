from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Any
from enum import Enum

OFFLINE_TIMEOUT = 3600 

class GroupTypeEnum(str, Enum):
    geolocation = 'geolocation'
    custom = 'custom'

# --- Group Schemas ---
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
    model_config = ConfigDict(from_attributes=True)

# --- Device Schemas ---
class DeviceCreate(BaseModel):
    serial: str
    type_id: int
    group_id: Optional[int] = None
    alias: Optional[str] = None
    description: Optional[str] = None

class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int

class DeviceUpdate(BaseModel):
    serial: Optional[str] = Field(None, min_length=1, max_length=50)
    type_id: Optional[int] = None 
    group_id: Optional[int] = Field(None, ge=1)
    alias: Optional[str] = None
    description: Optional[str] = None
    location: Any = None 

class DeviceTypeOut(BaseModel):
    id: int
    name: str
    icon: Optional[str]
    model_config = ConfigDict(from_attributes=True)

class DeviceTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None

class DeviceTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None

class DeviceOut(BaseModel):
    id: int
    serial: str
    alias: Optional[str]
    description: Optional[str]
    location: Any  
    total_work_time: int
    group_id: Optional[int]
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("location", mode="before")
    @classmethod
    def parse_location(cls, v: Any) -> Optional[List[float]]:
        if v is None:
            return None
        if isinstance(v, (tuple, list)):
            return [float(v[0]), float(v[1])]
        if isinstance(v, str):
            try:
                cleaned = v.replace("(", "").replace(")", "")
                coords = [float(x.strip()) for x in cleaned.split(",")]
                return coords
            except (ValueError, IndexError):
                return None
        return v

# --- Detail Schemas ---
class GroupDetail(GroupOut):
    devices: List[DeviceOut] = []

# class GroupDashboardOut(BaseModel):
#     id: int
#     name: str
#     type: GroupTypeEnum
#     # Статистика внутри группы
#     online_count: int
#     offline_count: int
#     # Список всех устройств этой группы
#     devices: List[DeviceOut] 
    
#     model_config = ConfigDict(from_attributes=True)


GroupDetail.model_rebuild()

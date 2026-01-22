from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Any
from enum import Enum

# --- Константы ---
OFFLINE_TIMEOUT = 3600 

# --- Enums ---
class GroupTypeEnum(str, Enum):
    geolocation = 'geolocation'
    custom = 'custom'
    geo = 'geo'

# --- Group Schemas ---
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: GroupTypeEnum

    project_id: Optional[int] = None 

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[GroupTypeEnum] = None

class GroupOut(BaseModel):
    id: int
    name: str
    type: GroupTypeEnum
    project_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)

# --- Device Type (Project) Schemas ---
class DeviceTypeOut(BaseModel):
    id: int
    name: str
    icon: Optional[str]
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class DeviceTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None

class DeviceTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None

# --- Device Schemas ---
class DeviceCreate(BaseModel):
    serial: str = Field(..., min_length=1, max_length=50)
    type_id: int
    group_id: Optional[int] = None
    alias: Optional[str] = None
    description: Optional[str] = None

class DeviceUpdate(BaseModel):
    serial: Optional[str] = Field(None, min_length=1, max_length=50)
    type_id: Optional[int] = None 
    group_id: Optional[int] = Field(None, ge=1)
    alias: Optional[str] = None
    description: Optional[str] = None
    location: Any = None 

class DeviceOut(BaseModel):
    id: int
    serial: str
    alias: Optional[str]
    description: Optional[str]
    location: Any  
    total_work_time: int = 0
    group_id: Optional[int]
    is_online: bool = False # <-- ВАЖНО: Добавили для фронтенда
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("location", mode="before")
    @classmethod
    def parse_location(cls, v: Any) -> Optional[List[float]]:
        if v is None:
            return None
        # Для Postgres Point (x, y)
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

# --- Analytics & Dashboard Schemas ---
class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int

class GroupAnalytics(BaseModel):
    name: str
    online: int
    offline: int

class ProjectDashboardOut(BaseModel):
    groups_stat: List[GroupAnalytics]
    total_stat: DeviceStats

# метрики и логи

class MetricMetadataBase(BaseModel):
    metric_name: str
    display_name_ru: Optional[str] = None
    display_name_en: Optional[str] = None
    icon_key: Optional[str] = None
    unit: Optional[str] = None

    min_threshold: Optional[float] = None 
    max_threshold: Optional[float] = None

class MetricMetadataOut(MetricMetadataBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

    min_threshold: Optional[float] = None 
    max_threshold: Optional[float] = None

class MetricDataPoint(BaseModel):
    time: int
    value: float

class MetricHistoryOut(BaseModel):
    metric_name: str
    display_name: Optional[str] = None # Возьмем из метаданных
    unit: Optional[str] = None         # Возьмем из метаданных
    history: List[MetricDataPoint]
    status: str = "normal"


class DeviceLogOut(BaseModel):
    timestamp: str  # Время события
    level: str      # INFO, ERROR, WARN
    message: str    # Текст лога

class DeviceLogsResponse(BaseModel):
    serial: str
    logs: List[DeviceLogOut]


class DeviceFullDetailOut(BaseModel):
    # Данные из PostgreSQL
    device_info: DeviceOut 
    # Данные из Prometheus (последние точки по ключевым метрикам)
    metrics: List[MetricHistoryOut] 
    # Данные из Loki
    logs: List[DeviceLogOut]

# --- Detail Schemas ---
class GroupDetail(GroupOut):
    devices: List[DeviceOut] = []

GroupDetail.model_rebuild()

from models import IssueTypeEnum
import models
from pydantic import BaseModel, Field, field_validator, ConfigDict, Json
from typing import Optional, List, Any, Dict
from enum import Enum
from datetime import datetime


# --- Константы ---
OFFLINE_TIMEOUT = 3600 

# --- Enums ---

class DeviceStatusEnum(str, Enum):
    OFFLINE = "off"
    ONLINE = "on"
    PROBLEMATIC = "problematic"

# --- Group Schemas ---
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    project_id: Optional[int] = None 

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)

class GroupOut(BaseModel):
    id: int
    name: str
    project_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)

# --- Project Schemas ---
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class ProjectOut(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class IssuePreview(BaseModel):
    id: int
    name: str
    type: IssueTypeEnum
    occurrence: datetime
    
    model_config = ConfigDict(from_attributes=True)

class TracePreview(BaseModel):
    id: int
    device_id: int
    issue_id: int
    occurrence: datetime
    
    model_config = ConfigDict(from_attributes=True)

class TraceFull(TracePreview):
    occurrence: datetime
 


class IssueFull(BaseModel):
    id: int
    name: str
    type: IssueTypeEnum
    traces: List[TracePreview]
     
    model_config = ConfigDict(from_attributes=True)


# --- Device Schemas ---
class DeviceCreate(BaseModel):
    serial: str = Field(..., min_length=1, max_length=50)
    group_id: Optional[int] = None
    description: Optional[str] = None
    notes: Optional[str] = None

class DeviceUpdate(BaseModel):
    serial: Optional[str] = Field(None, min_length=1, max_length=50)
    group_id: Optional[int] = Field(None, ge=1)
    description: Optional[str] = None
    location: Any = None 
    notes: Optional[str] = None

class DeviceOut(BaseModel):
    id: int
    serial: str
    description: Optional[str]
    notes: Optional[str] = None

    location: Any  
    total_work_time: int = 0
    group_id: Optional[int]
    
    status: DeviceStatusEnum
    
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

    issues: List[IssuePreview]


class ActiveAlert(BaseModel):
    alertname: str
    severity: str
    summary: str
    description: str
    active_at: str

class DeviceAlerts(BaseModel):
    serial: str
    # alias: Optional[str]
    alerts: List[ActiveAlert]

class GroupedAlertsOut(BaseModel):
    # Группировка: Имя группы -> Список устройств с их алертами
    groups: dict[str, List[DeviceAlerts]]

class AlertWithMetadata(BaseModel):
    alertname: str
    severity: str
    summary: str
    description: str
    active_at: str

    serial: str

class GroupDetail(BaseModel):
    id: int
    name: str
    project_id: int
    devices: List[DeviceOut]  
    
    model_config = ConfigDict(from_attributes=True)

class ModelDeviceAnomalies(BaseModel):
    status: str
    anomalies_count: int
    critical_points: str
    
GroupDetail.model_rebuild()

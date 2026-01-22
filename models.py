from sqlalchemy import Column, Integer, String, DateTime, Float, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.types import UserDefinedType
from datetime import datetime, timezone
from database import Base
import enum

class GroupEnum(str, enum.Enum):
    geolocat = 'geolocation'
    type = 'type'
    status = 'status'

class Point(UserDefinedType):
    def get_col_spec(self):
        return 'POINT'

class GroupTypeEnum(enum.Enum):
    geolocation = 'geolocation'
    custom = 'custom'
    geo = 'geo' 

class DeviceType(Base):
    __tablename__ = 'device_types'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # напр. "Сушилка модель Х"
    description = Column(String)
    icon = Column(String) # общая иконка для всех устройств этого типа
    
    devices = relationship("Device", back_populates="device_type")

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, nullable=False, index=True) 
    type_id = Column(Integer, ForeignKey('device_types.id'), nullable=True)
    device_type = relationship("DeviceType", back_populates="devices")

    total_work_time = Column(Integer, default=0, server_default="0")

    location = Column(Point, nullable=True)  # ???
    alias = Column(String)             # например "сушилка в цеху №1"
    description = Column(String)       # например "обслуживается по понедельникам"

    # TODO: user / org
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    group = relationship("Group", back_populates="devices")



class MetricMetadata(Base):
    __tablename__ = 'metric_metadata'

    id = Column(Integer, primary_key=True)
    metric_name = Column(String, unique=True, index=True) # 'temp'
    
    display_name_ru = Column(String)  
    display_name_en = Column(String)  
    icon_key = Column(String)         
    unit = Column(String)             # '°C'

class Project(Base):
    __tablename__='projects'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(Enum(GroupTypeEnum), default=GroupTypeEnum.custom)
    
    devices = relationship("Device", back_populates="group")

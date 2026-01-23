from sqlalchemy import Column, Integer, String, DateTime, Float, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.types import UserDefinedType
from datetime import datetime, timezone
from database import Base
import enum

class Point(UserDefinedType):
    def get_col_spec(self):
        return 'POINT'

class GroupTypeEnum(enum.Enum):
    geolocation = 'geolocation'
    custom = 'custom'
    geo = 'geo' 

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, nullable=False, index=True) 
    total_work_time = Column(Integer, default=0, server_default="0")

    location = Column(Point, nullable=True)  # ???
    alias = Column(String)             # например "сушилка в цеху №1"
    description = Column(String)       # например "обслуживается по понедельникам"
    last_sync = Column(DateTime, nullable=True)

    notes = Column(String)

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

    min_threshold = Column(Float, nullable=True) # Минимальный порог
    max_threshold = Column(Float, nullable=True) # Максимальный порог

class Project(Base):
    __tablename__='projects'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    groups = relationship("Group", back_populates="project")

class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(Enum(GroupTypeEnum), default=GroupTypeEnum.custom)
    
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    project = relationship("Project", back_populates="groups")
    
    devices = relationship("Device", back_populates="group")

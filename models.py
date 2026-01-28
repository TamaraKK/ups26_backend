from sqlalchemy import Column, Integer, String, DateTime, Float, Date, Enum, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import UserDefinedType
from datetime import datetime, timezone
from database import Base
import enum

class Point(UserDefinedType):
    def get_col_spec(self):
        return 'POINT'

# Define the IssueTypeEnum first
class IssueTypeEnum(enum.Enum):
    abort = 'abort'
    assertion = 'assert'
    watchdog = 'watchdog'

class Trace(Base):
    __tablename__ = 'traces'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(Integer, ForeignKey('issues.id'))
    device_id = Column(Integer, ForeignKey('devices.id'))
    core_dump = Column(JSON)
    occurrence = Column(DateTime, default=datetime.now)
    
    issue = relationship("Issue", back_populates="traces")
    device = relationship("Device", back_populates="traces")

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
    
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    project = relationship("Project", back_populates="groups")
    
    devices = relationship("Device", back_populates="group")

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, nullable=False, index=True) 
    total_work_time = Column(Integer, default=0, server_default="0")
    location = Column(Point, nullable=True)
    description = Column(String)
    last_sync = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    
    # Relationships
    group = relationship("Group", back_populates="devices")
    
    # Many-to-many with Issue through Trace table
    issues = relationship(
        'Issue', 
        secondary=Trace.__table__, 
        back_populates='devices',
        overlaps="traces"  # Add overlaps parameter
    )
    
    # One-to-many to Trace
    traces = relationship("Trace", back_populates="device")

class Issue(Base):
    __tablename__ = 'issues'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True) 
    type = Column(Enum(IssueTypeEnum))
    
    # Many-to-many with Device through Trace table
    devices = relationship(
        'Device', 
        secondary=Trace.__table__, 
        back_populates='issues',
        overlaps="traces"  # Add overlaps parameter
    )
    
    # One-to-many to Trace
    traces = relationship("Trace", back_populates="issue")

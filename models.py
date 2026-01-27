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

# Define the association table BEFORE the classes that reference it
IssueDevice = Table(
    'issue_device',
    Base.metadata,
    Column('issue_id', Integer, ForeignKey('issues.id'), primary_key=True),
    Column('device_id', Integer, ForeignKey('devices.id'), primary_key=True),
    Column('occurrence_count', Integer, default=1, nullable=False), 
    Column('first_occurrence', DateTime, default=datetime.now), 
    Column('last_occurrence', DateTime, default=datetime.now, 
           onupdate=datetime.now), 
)

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

# Define Device BEFORE Issue since Issue references Device in relationship
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
    
    # Use string reference 'Issue' since Issue is not defined yet
    issues = relationship('Issue', secondary=IssueDevice, back_populates='devices')

class Issue(Base):
    __tablename__ = 'issues'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True) 
    data = Column(JSON)
    type = Column(Enum(IssueTypeEnum))
    
    # Use string reference 'Device' (already defined)
    devices = relationship('Device', secondary=IssueDevice, back_populates='issues')

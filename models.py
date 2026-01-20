from sqlalchemy import Column, Integer, String, DateTime, Float, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class GroupEnum(str, enum.Enum):
    geo = 'geolocation'
    type = 'type'
    status = 'status'

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    group = relationship("Group", back_populates="devices")


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    devices = relationship("Device", back_populates="group")
    type = Column(Enum(GroupEnum))

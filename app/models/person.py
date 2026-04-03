import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Integer, Date, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.database import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(Text, nullable=False)
    birth_year = Column(Integer, nullable=True)
    death_year = Column(Integer, nullable=True)
    region = Column(Text, nullable=True)
    district = Column(Text, nullable=True)
    occupation = Column(Text, nullable=True)
    charge = Column(Text, nullable=True)
    arrest_date = Column(Date, nullable=True)
    sentence = Column(Text, nullable=True)
    sentence_date = Column(Date, nullable=True)
    rehabilitation_date = Column(Date, nullable=True)
    biography = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending | verified | rejected
    name_embedding = Column(Vector(1536), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

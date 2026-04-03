import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from pydantic import BaseModel

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(Text, nullable=False)
    file_type = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending | processing | processed | failed_extraction
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.utcnow)
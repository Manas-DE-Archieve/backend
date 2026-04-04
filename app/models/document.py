import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Text, ForeignKey, String, Float
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(Text, nullable=False)
    file_type = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)

    # Processing status: pending | processing | processed | failed_extraction
    status = Column(String(20), default="pending")

    # Moderation status: pending | verified | rejected | auto_rejected
    verification_status = Column(String(20), default="verified")

    # Similarity score (0.0–1.0) against existing docs at upload time
    similarity_score = Column(Float, nullable=True)

    # Which document it's most similar to
    duplicate_of_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)

    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    content_hash = Column(Text, nullable=True, unique=True)
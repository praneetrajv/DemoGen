"""
Database Models using SQLAlchemy
Handles PostgreSQL schema definition
"""

from sqlalchemy import Column, String, Integer, DateTime, JSON, Boolean, Float, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class DemoSession(Base):
    """Demo generation session"""
    __tablename__ = "demo_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)
    prompt = Column(Text, nullable=False)
    language = Column(String, default="en")
    feature = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    videos = relationship("VideoAsset", back_populates="session")
    automation_logs = relationship("AutomationLog", back_populates="session")
    
    def __repr__(self):
        return f"<DemoSession(id={self.id}, status={self.status})>"


class VideoAsset(Base):
    """Generated video asset"""
    __tablename__ = "video_assets"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("demo_sessions.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)  # seconds
    resolution = Column(String, nullable=True)  # e.g., "1080p"
    fps = Column(Integer, nullable=True)
    format = Column(String, default="mp4")
    has_audio = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    storage_type = Column(String, default="local")  # local, s3, gcs, azure
    storage_path = Column(String, nullable=True)
    
    # Relationships
    session = relationship("DemoSession", back_populates="videos")
    validation = relationship("VideoValidation", uselist=False, back_populates="video")
    
    def __repr__(self):
        return f"<VideoAsset(id={self.id}, duration={self.duration}s)>"


class VideoValidation(Base):
    """Video quality validation results"""
    __tablename__ = "video_validations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String, ForeignKey("video_assets.id"), nullable=False)
    quality_score = Column(Float, nullable=True)  # 0-100
    is_approved = Column(Boolean, default=False)
    validation_result = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    validated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    video = relationship("VideoAsset", back_populates="validation")
    
    def __repr__(self):
        return f"<VideoValidation(video_id={self.video_id}, score={self.quality_score})>"


class AutomationLog(Base):
    """Playwright automation execution log"""
    __tablename__ = "automation_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("demo_sessions.id"), nullable=False)
    action_type = Column(String, nullable=False)  # navigate, click, fill, scroll, etc.
    selector = Column(String, nullable=True)
    value = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, executing, completed, failed
    error_message = Column(Text, nullable=True)
    screenshot_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    execution_time_ms = Column(Integer, nullable=True)
    
    # Relationships
    session = relationship("DemoSession", back_populates="automation_logs")
    
    def __repr__(self):
        return f"<AutomationLog(action={self.action_type}, status={self.status})>"


class DOMSnapshot(Base):
    """Stored DOM snapshots for drift detection"""
    __tablename__ = "dom_snapshots"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portal_url = Column(String, nullable=False)
    feature_name = Column(String, nullable=True)
    dom_hash = Column(String, nullable=False)
    dom_structure = Column(JSON, nullable=True)
    element_count = Column(Integer, nullable=True)
    screenshot_path = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)
    is_latest = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<DOMSnapshot(portal_url={self.portal_url}, hash={self.dom_hash[:8]})>"


class DriftDetection(Base):
    """UI drift detection results"""
    __tablename__ = "drift_detections"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portal_url = Column(String, nullable=False)
    feature_name = Column(String, nullable=True)
    drift_type = Column(String)  # "element_moved", "element_removed", "element_added", "visual_changed"
    element_selector = Column(String, nullable=True)
    old_position = Column(JSON, nullable=True)  # {x, y, width, height}
    new_position = Column(JSON, nullable=True)
    similarity_score = Column(Float, nullable=True)  # 0-1
    detected_at = Column(DateTime, default=datetime.utcnow)
    action_taken = Column(String, nullable=True)  # "regenerate_video", "flagged_for_review"
    
    def __repr__(self):
        return f"<DriftDetection(type={self.drift_type}, score={self.similarity_score})>"


class NarrationScript(Base):
    """Generated narration scripts"""
    __tablename__ = "narration_scripts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("demo_sessions.id"), nullable=True)
    feature_name = Column(String, nullable=True)
    language = Column(String, default="en")
    script_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)
    duration_estimate_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<NarrationScript(language={self.language}, words={self.word_count})>"

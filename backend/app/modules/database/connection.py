"""
Database Connection and Session Management
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from config import settings
from .models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self.init()
    
    def init(self):
        """Initialize database connection"""
        try:
            if not settings.database_url:
                logger.info("Database not configured - skipping initialization")
                self.engine = None
                self.SessionLocal = None
                return
            
            self.engine = create_engine(
                settings.database_url,
                echo=settings.app_debug,
                poolclass=NullPool
            )
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            logger.info("Database connection initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            self.engine = None
            self.SessionLocal = None
    
    def create_tables(self):
        """Create all tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
    
    def get_session(self) -> Session:
        """Get database session"""
        if self.SessionLocal is None:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")


# Global database instance
db = Database()


def get_db() -> Session:
    """Dependency injection for database session"""
    db_session = db.get_session()
    try:
        yield db_session
    finally:
        db_session.close()

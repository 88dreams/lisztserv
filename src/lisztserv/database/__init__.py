from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
import os
from urllib.parse import quote_plus

Base = declarative_base()

def get_database_url():
    """Get database URL from environment with proper credentials handling."""
    # Priority: Explicit DATABASE_URL > Individual connection params
    if 'DATABASE_URL' in os.environ:
        return os.environ['DATABASE_URL']
    
    # Construct from individual parameters
    db_user = os.environ.get('DB_USER', '')
    db_password = os.environ.get('DB_PASSWORD', '')
    db_host = os.environ.get('DB_HOST', '')
    db_port = os.environ.get('DB_PORT', '5432')  # Default PostgreSQL port
    db_name = os.environ.get('DB_NAME', '')
    
    if all([db_user, db_password, db_host, db_name]):
        # Create PostgreSQL connection string
        return f"postgresql://{quote_plus(db_user)}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}"
    
    raise ValueError("Database configuration not found. Please set DATABASE_URL or individual database parameters.")

def create_db_engine():
    """Create database engine with proper configuration."""
    database_url = get_database_url()
    
    # Configure connection pooling
    engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=5,  # Base number of connections
        max_overflow=10,  # Additional connections when pool is full
        pool_timeout=30,  # Seconds to wait for available connection
        pool_recycle=1800,  # Recycle connections after 30 minutes
        pool_pre_ping=True,  # Verify connection before using
        echo=False  # Set to True for SQL query logging
    )
    
    return engine

# Create engine and session factory
try:
    engine = create_db_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    raise RuntimeError(f"Failed to initialize database: {str(e)}")

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine) 
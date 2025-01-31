from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Load environment variables
env_path = Path(__file__).parent.parent.parent.parent / '.env'
load_dotenv(env_path)

Base = declarative_base()

def get_database_url():
    """Get database URL from environment with proper credentials handling."""
    # Priority: Explicit DATABASE_URL > Individual connection params
    if 'DATABASE_URL' in os.environ:
        return os.environ['DATABASE_URL']
    
    # Construct from individual parameters
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT', '5432')  # Default PostgreSQL port
    db_name = os.environ.get('DB_NAME')
    
    if not all([db_user, db_password, db_host, db_name]):
        print("Database configuration values:")
        print(f"DB_USER: {'set' if db_user else 'not set'}")
        print(f"DB_PASSWORD: {'set' if db_password else 'not set'}")
        print(f"DB_HOST: {'set' if db_host else 'not set'}")
        print(f"DB_PORT: {db_port}")
        print(f"DB_NAME: {'set' if db_name else 'not set'}")
        raise ValueError("Database configuration not found. Please check your .env file.")
    
    # Create PostgreSQL connection string
    return f"postgresql://{quote_plus(db_user)}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}"

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
    print(f"Database initialization error: {str(e)}")
    raise RuntimeError(f"Failed to initialize database: {str(e)}")

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(database_url: str):
    """Initialize the database with async support."""
    engine = create_async_engine(database_url)
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    return engine, async_session

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine) 
from sqlalchemy import text
from . import create_db_engine, get_database_url
import sys

def test_database_connection():
    """Test the database connection and configuration."""
    print("\nTesting Database Connection")
    print("-------------------------")
    
    try:
        # Get database URL
        db_url = get_database_url()
        print(f"Database URL format: {db_url.split('@')[0].split(':')[0]}://<user>:******@{db_url.split('@')[1]}")
        
        # Create engine
        print("\nCreating database engine...")
        engine = create_db_engine()
        
        # Test connection
        print("Testing connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.scalar()
            
            print("\nConnection successful!")
            print(f"PostgreSQL version: {version}")
            
            # Test query execution
            print("\nTesting query execution...")
            result = conn.execute(text("SELECT current_timestamp;"))
            timestamp = result.scalar()
            print(f"Current database timestamp: {timestamp}")
            
        return True
        
    except Exception as e:
        print("\nError connecting to database:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1) 
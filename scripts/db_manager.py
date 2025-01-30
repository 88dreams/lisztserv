import os
import sys
import subprocess
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables first
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent directory to path to import lisztserv
sys.path.append(str(Path(__file__).parent.parent))

# Now import database modules after environment is loaded
from lisztserv.database import Base, create_db_engine

def load_env():
    """Load environment variables from .env file"""
    return {
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT'),
        'database': os.getenv('DB_NAME')
    }

def create_database():
    """Create the database if it doesn't exist"""
    config = load_env()
    
    # Connect to default postgres database to create new database
    try:
        print(f"Connecting to default 'postgres' database to create {config['database']}...")
        conn = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            database='postgres'  # Connect to default postgres database first
        )
        conn.autocommit = True
        
        cur = conn.cursor()
        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config['database'],))
        exists = cur.fetchone()
        
        if not exists:
            print(f"Creating database {config['database']}...")
            # Escape the database name to prevent SQL injection
            db_name = config['database'].replace('"', '""')
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print("Database created successfully!")
        else:
            print(f"Database {config['database']} already exists.")
            
    except Exception as e:
        print(f"Error creating database: {e}")
        raise
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

def setup_database():
    """Set up the database schema"""
    try:
        # Create database if it doesn't exist
        create_database()
        
        # Create tables
        engine = create_db_engine()
        Base.metadata.create_all(engine)
        print("Database tables created successfully!")
        
    except Exception as e:
        print(f"Error setting up database: {e}")

def run_migrations():
    """Run all pending migrations"""
    try:
        result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Migrations completed successfully!")
        else:
            print(f"Error running migrations: {result.stderr}")
    except Exception as e:
        print(f"Error running migrations: {e}")

def main():
    """Main function to manage database operations"""
    if len(sys.argv) < 2:
        print("Usage: python db_manager.py [setup|migrate]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'setup':
        setup_database()
    elif command == 'migrate':
        run_migrations()
    else:
        print(f"Unknown command: {command}")

if __name__ == '__main__':
    main() 
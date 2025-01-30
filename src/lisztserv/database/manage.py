import os
import sys
from alembic.config import Config
from alembic import command
from pathlib import Path

def get_alembic_config():
    """Get Alembic configuration."""
    # Get the path to the alembic.ini file
    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini = project_root / 'alembic.ini'
    
    if not alembic_ini.exists():
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")
    
    return Config(str(alembic_ini))

def run_migrations():
    """Run all pending migrations."""
    print("\nRunning database migrations...")
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head")
        print("Migrations completed successfully!")
        return True
    except Exception as e:
        print(f"Error running migrations: {str(e)}")
        return False

def rollback_migration(steps=1):
    """Rollback the specified number of migrations."""
    print(f"\nRolling back {steps} migration(s)...")
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, f"-{steps}")
        print("Rollback completed successfully!")
        return True
    except Exception as e:
        print(f"Error rolling back migrations: {str(e)}")
        return False

def create_migration(message):
    """Create a new migration."""
    print("\nCreating new migration...")
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, autogenerate=True, message=message)
        print("Migration created successfully!")
        return True
    except Exception as e:
        print(f"Error creating migration: {str(e)}")
        return False

def show_migration_history():
    """Show migration history."""
    print("\nMigration History:")
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg)
        return True
    except Exception as e:
        print(f"Error showing migration history: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python manage.py migrate           # Run all pending migrations")
        print("  python manage.py rollback [steps]  # Rollback migrations")
        print("  python manage.py create 'message'  # Create new migration")
        print("  python manage.py history           # Show migration history")
        sys.exit(1)
        
    command = sys.argv[1]
    success = False
    
    if command == "migrate":
        success = run_migrations()
    elif command == "rollback":
        steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        success = rollback_migration(steps)
    elif command == "create":
        if len(sys.argv) < 3:
            print("Error: Migration message required")
            sys.exit(1)
        success = create_migration(sys.argv[2])
    elif command == "history":
        success = show_migration_history()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
        
    sys.exit(0 if success else 1) 
# main.py
import sys

# Enforce UTF-8 safely to avoid local system terminal encoding crashes
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Initialize paths and load environment variables
from utils.path_helper import load_env_file
load_env_file()

from database.table_generator import create_tables
from cli.menu_flows import run_main_app_loop

def run_assistant_cli() -> None:
    """Boots the local assistant backend systems and enters the main loop."""
    print("Initializing local assistant database...")
    try:
        create_tables()
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)
    
    # Launch main application menu flow
    run_main_app_loop()

if __name__ == "__main__":
    run_assistant_cli()
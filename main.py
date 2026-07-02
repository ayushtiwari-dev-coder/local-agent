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
from managers.recovery_manager import ExecutionRecoveryManager
from tools.orchestra_tools import register_orchestra_status_callback
from cli.callbacks import cli_status_callback
from cli.menu_flows import run_main_app_loop

def run_assistant_cli() -> None:
    """Boots the local assistant backend systems and enters the main loop."""
    print("Initializing local assistant database...")
    try:
        create_tables()
        # Clean up orphaned background tasks from abnormal shutdowns
        ExecutionRecoveryManager.recover_orphaned_tasks()
        
        # Register the status callback inside the orchestrator
        register_orchestra_status_callback(cli_status_callback)
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)
        
    # Launch main application menu flow
    run_main_app_loop()

if __name__ == "__main__":
    run_assistant_cli()
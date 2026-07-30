# main.py
import sys
import os

# Enforce UTF-8 safely to avoid local system terminal encoding crashes
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

def configure_dynamic_workspace():
    """
    Detects the current terminal directory. If it's a specific project folder,
    it locks the agent's workspace to that folder. If it's a generic system path,
    it falls back to the default sandbox.
    """
    cwd = os.path.abspath(os.getcwd())
    home = os.path.abspath(os.path.expanduser("~"))
    drive_root = os.path.abspath(os.sep)  # e.g., C:\ or /
    windir = os.environ.get("WINDIR", "C:\\Windows")
    
    # Define what constitutes a "generic" directory where we shouldn't drop files
    is_drive_root = (cwd == drive_root)
    is_home = (cwd == home)
    is_system = cwd.lower().startswith(windir.lower())
    
    if is_drive_root or is_home or is_system:
        print("[*] Generic system directory detected. Using default sandbox workspace.")
    else:
        # We are in a specific folder. Override workspace in memory.
        os.environ["AGENT_WORKSPACE_OVERRIDE"] = cwd
        print(f"[*] Dynamic Workspace Active: {cwd}")

# Execute detection before loading the rest of the app
configure_dynamic_workspace()

# Initialize paths and load environment variables
from utils.path_helper import load_env_file
load_env_file()

from database.table_generator import create_tables
from cli.menu_flows import run_main_app_loop

def main():
    """Main Entrypoint for the Local Workflow Agent."""
    print("Initializing local assistant database...")
    try:
        create_tables()
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)

    # Directly launch the CLI interface
    run_main_app_loop()

if __name__ == "__main__":
    main()
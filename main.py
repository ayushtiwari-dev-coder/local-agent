# FILE: test_main.py

import sys
# Import the path helper first
from utils.path_helper import load_env_file

# Load environment variables (API keys) immediately on startup
load_env_file()

# Absolute imports from our packages
from database.table_generator import create_tables
from managers.user_manager import get_active_user, register_user
from managers.conversation_manager import start_new_conversation

# --> USE THE NEW TEST ENGINE <--
from engine.agent_engine import AgentEngine

def cli_tool_approval_callback(tool_name: str, arguments: dict) -> bool:
    """ Passed to the Engine to handle terminal user authorization. """
    print(f"\n 📝 [AI Requests Tool Run] -> {tool_name}")
    print(f"    Parameters: {arguments}")
    choice = input("👉 Allow this action? (y/n): ").strip().lower()
    return choice == "y"

def cli_status_callback(message: str) -> None:
    """Prints system-level status and retry updates to the console."""
    print(f"⚙️ [System Status] {message}")

def run_assistant_cli() -> None:
    """ The main CLI loop that boots the system. """
    print("Initializing local assistant database...")
    try:
        create_tables()
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)

    # Verify or Register Active User
    user = get_active_user()
    if user is None:
        print("\n--- Welcome to Local Workflow Agent! ---")
        print("Let's set up your local profile first.")
        while True:
            try:
                name = input("Enter your Display Name (e.g. Ayush): ")
                username = input("Enter your unique Username (e.g. ayush_tiwari): ")
                user = register_user(name, username)
                print(f"\nSuccess: Profile created for {user['name']} (@{user['username']})!")
                break
            except ValueError as e:
                print(f"Validation Error: {e}. Please try again.\n")

    # Start or load a central Conversation Session
    try:
        session = start_new_conversation(user_id=user["id"], title="Active Terminal Session")
        conversation_id = session["id"]
    except Exception as e:
        print(f"Fatal: Failed to start conversation session: {e}")
        sys.exit(1)

    # Instantiate our NEW Agent Engine
    try:
        # Default provider is Gemini, but architecture supports others now
        engine = AgentEngine(provider_name="gemini", autonomous=False)
    except Exception as e:
        print(f"Initialization Error: {e}")
        print("Please make sure you have set the GEMINI_API_KEY inside your .env file.")
        sys.exit(1)

    print(f"\n=== Hello, {user['name']}! Your new abstract local-first agent is ready. ===")
    print("Type 'exit' or 'quit' to close the session.\n")

    # The Interactive Chat Loop
    while True:
        try:
            user_input = input("👤 You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            print("🤖 Assistant is thinking...")
            response_text = engine.send_message(
                conversation_id=conversation_id, 
                user_text=user_input, 
                approval_callback=cli_tool_approval_callback, 
                status_callback=cli_status_callback
            )
            print(f"\n 🤖 Assistant: {response_text}\n")
            
        except KeyboardInterrupt:
            print("\nSession interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n ❌ Error encountered: {e}\n")
            raise

if __name__ == "__main__":
    run_assistant_cli()
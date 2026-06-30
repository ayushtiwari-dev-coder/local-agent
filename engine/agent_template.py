# engine/agent_template.py
from engine.agent_profiles import AGENT_PROFILES
from utils import config_manager

class AgentTemplate:
    @staticmethod
    def spawn(role_name: str, autonomous: bool = True):
        """
        Dynamically instantiates an AgentEngine pre-configured for a specialized role
        using the database-driven model routing configuration.
        """
        profile = AGENT_PROFILES.get(role_name)
        if not profile:
            raise ValueError(f"Agent profile '{role_name}' does not exist.")
            
        # 1. Fetch dynamic model routing for this specific role (Manager, Planner, Executor) [52]
        route = config_manager.get_orchestra_route(role_name)
        
        provider = route.get("provider", "gemini")
        model = route.get("model", "gemini-3.1-flash-lite")
        api_key = config_manager.get_provider_api_key(provider) # [53]
        
        # 2. BREAK CIRCULAR IMPORT: Import AgentEngine inline at runtime [16]
        from engine.agent_engine import AgentEngine
        
        # 3. Instantiate and return the standard AgentEngine [16]
        return AgentEngine(
            provider_name=provider,
            model_name=model,
            api_key=api_key,
            autonomous=autonomous
        )
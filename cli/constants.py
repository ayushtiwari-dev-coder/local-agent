# cli/constants.py

SEPARATOR = "━" * 80

APP_BANNER = """[bold cyan]
██╗      ██████╗  ██████╗ █████╗ ██╗         █████╗ ██████╗ ███████╗███╗   ██╗████████╗
██║     ██╔═══██╗██╔════╝██╔══██╗██║        ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
██║     ██║   ██║██║     ███████║██║        ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
██║     ██║   ██║██║     ██╔══██║██║        ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
███████╗╚██████╔╝╚██████╗██║  ██║███████╗   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
[/bold cyan]"""

ROLE_ICONS = {
    "user": "👤 You",
    "assistant": "🤖 Agent",
    "system": "⚙️ System",
}

IN_CHAT_HELP = """
[bold cyan]Available Chat Commands:[/bold cyan]
  [bold yellow]/menu[/bold yellow]     - Go back to the main menu
  [bold yellow]/settings[/bold yellow] - Open the advanced settings dashboard (Limits, Prompts, etc.)
  [bold yellow]/models[/bold yellow]   - Quick switch your active AI model and Embeddings
  [bold yellow]/think[/bold yellow]    - Adjust the agent's thinking/reasoning level
  [bold yellow]/tools[/bold yellow]    - Show just the tool calls made in this conversation
  [bold yellow]/history[/bold yellow]  - Reprint the full transcript of this conversation
  [bold yellow]/search[/bold yellow]   - Search your long-term memories database
  [bold yellow]/research[/bold yellow] - Trigger Deep Research mode for a specific topic
  [bold yellow]/clear[/bold yellow]    - Clear the terminal screen
  [bold yellow]/delete[/bold yellow]   - Delete current active conversation thread immediately
  [bold yellow]/exit[/bold yellow]     - Save and exit the agent
"""

SUPPORTED_MODELS = {
    "gemini": [
        {"model": "gemini-3.1-flash-lite", "desc": "Gemini 3.1 Flashlight (Ultra-low latency, supports thinking)"},
        {"model": "gemini-2.5-flash-lite", "desc": "Gemini 2.5 Flashlight (Fast, cost-efficient, stable)"},
        {"model": "gemini-2.5-flash", "desc": "Gemini 2.5 Flash (State-of-the-art workhorse model)"},
        {"model": "gemini-3-flash", "desc": "Gemini 3 Flash (Advanced reasoning combined with Flash speed)"},
        {"model": "gemini-3.5-flash", "desc": "Gemini 3.5 Flash (Frontier-class performance with agentic capabilities)"},
        {"model": "gemma-4-26b-a4b-it", "desc": "Gemma 4 26B (Mixture-of-Experts reasoning open model)"},
        {"model": "gemma-4-31b-it", "desc": "Gemma 4 31B (Flagship dense open reasoning model)"},
    ],
    "groq": [
        {"model": "llama-3.3-70b-versatile", "desc": "Llama 3.3 70B Versatile (Stable, high intelligence Meta production standard)"},
        {"model": "openai/gpt-oss-120b", "desc": "GPT-OSS 120B (OpenAI's flagship 120B open-weights model with native reasoning)"},
        {"model": "openai/gpt-oss-20b", "desc": "GPT-OSS 20B (OpenAI's highly efficient 20B open-weights reasoning model)"},
        {"model": "llama-3.1-8b-instant", "desc": "Llama 3.1 8B Instant (Extremely fast, ultra-low latency model)"},
    ],
}

SUPPORTED_EMBEDDING_MODELS = {
    "gemini": [
        {"model": "gemini-embedding-001", "desc": "Standard stable text embedding model"},
        {"model": "gemini-embedding-2", "desc": "Newest, high-performance multimodal-capable embedding model"},
    ],
    "groq": [
        {"model": "nomic-embed-text-v1.5", "desc": "Groq's ultra-fast, high-accuracy open text embedding model"},
    ]
}
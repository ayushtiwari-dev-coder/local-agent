# setup.py
from setuptools import setup

setup(
    name="local-workflow-agent",
    version="0.1.0",
    # Explicitly naming every package directory in the codebase
    packages=[
        "cli",
        "config_configure",
        "database",
        "engine",
        "llm",
        "llm.providers",
        "managers",
        "optional_docker_extension",
        "queries",
        "security",
        "tools",
        "utils",
        "utils.config"
    ],
    # Explicitly include main.py as it sits at the root outside a package
    py_modules=["main"],
    # All external dependencies extracted from your codebase imports
    install_requires=[
        "requests",
        "rich",
        "google-genai",
        "groq",
        "tiktoken",
        "docker",
        "markdown",
        "xhtml2pdf",
        "duckduckgo-search", # For DDGS
        "python-dotenv"
    ],
    entry_points={
        "console_scripts": [
            "agent=main:main",
        ],
    },
)
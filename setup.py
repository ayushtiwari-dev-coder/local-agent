from setuptools import setup, find_packages

setup(
    name="local-workflow-agent",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "rich",
        "prompt_toolkit",
        "google-genai",
        "groq",
        "beautifulsoup4",
        "markdown",
        "xhtml2pdf",
        "python-dotenv"
    ],
    entry_points={
        "console_scripts": [
            "agent=main:main",
        ],
    },
)
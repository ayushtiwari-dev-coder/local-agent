# setup.py
import os
from setuptools import setup, find_packages

# 1. Safely resolve the absolute path to requirements.txt
here = os.path.abspath(os.path.dirname(__file__))
req_path = os.path.join(here, "requirements.txt")

# 2. Parse requirements.txt, ignoring comments and empty lines
requirements = []
if os.path.exists(req_path):
    with open(req_path, "r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.strip()
            # Ignore empty lines and comments
            if clean_line and not clean_line.startswith("#"):
                requirements.append(clean_line)

setup(
    name="local-workflow-agent",
    version="0.1.0",
    
    # 3. Dynamically find all packages (ignores .venv, .pytest_cache automatically)
    # We explicitly exclude the "tests" folder so it doesn't ship with the app.
    packages=find_packages(exclude=["tests", "tests.*"]),
    
    # Explicitly include main.py as it sits at the root
    py_modules=["main"],
    
    # 4. Inject the dynamically parsed requirements
    install_requires=requirements,
    
    entry_points={
        "console_scripts": [
            "agent=main:main",
        ],
    },
)
# cli/security_rules.py
"""Defines system-wide security constraints and tool blocklists."""

UNSAFE_TOOLS = {"run_script", "manage_dependencies","write_files", "edit_file_chunk"}

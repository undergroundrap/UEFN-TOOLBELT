"""
fileSuggestion command — outputs key UEFN Toolbelt files for @ mention in Claude Code.
Runs when the user types @ in the prompt box.
"""
files = [
    "Content/Python/UEFN_Toolbelt/__init__.py",
    "Content/Python/UEFN_Toolbelt/tools/__init__.py",
    "Content/Python/UEFN_Toolbelt/core/__init__.py",
    "scripts/drift_check.py",
    "deploy.bat",
    "CLAUDE.md",
    "TOOL_STATUS.md",
    "ARCHITECTURE.md",
    "docs/UEFN_QUIRKS.md",
    "docs/PIPELINE.md",
    "docs/ui_style_guide.md",
    ".claude/tool_tables.md",
    ".claude/mcp_reference.md",
    "mcp_server.py",
    "client.py",
]

print("\n".join(files))

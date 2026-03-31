"""
PostToolUse hook — runs after Edit/Write tool calls.
If the edited file is a Python tool, validate syntax immediately.
Claude Code passes tool context via CLAUDE_TOOL_NAME and CLAUDE_TOOL_INPUT env vars.
"""
import os
import ast
import json
import sys

tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
tool_input_raw = os.environ.get("CLAUDE_TOOL_INPUT", "{}")

# Only act on file edit/write operations
if tool_name not in ("Edit", "Write", "MultiEdit"):
    sys.exit(0)

try:
    tool_input = json.loads(tool_input_raw)
except Exception:
    sys.exit(0)

file_path = tool_input.get("file_path", "")

# Only validate Python files inside the tools directory
if not file_path.endswith(".py"):
    sys.exit(0)

normalized = file_path.replace("\\", "/")
if "UEFN_Toolbelt/tools" not in normalized and "UEFN_Toolbelt/__init__" not in normalized:
    sys.exit(0)

# Syntax check
try:
    with open(file_path, encoding="utf-8") as f:
        source = f.read()
    ast.parse(source)
    # Clean — output nothing (no noise on success)
except SyntaxError as e:
    # Output structured feedback — Claude Code surfaces this to the model
    print(json.dumps({
        "type": "text",
        "text": f"SYNTAX ERROR in {os.path.basename(file_path)} line {e.lineno}: {e.msg}. Fix before continuing."
    }))
    sys.exit(1)
except FileNotFoundError:
    sys.exit(0)

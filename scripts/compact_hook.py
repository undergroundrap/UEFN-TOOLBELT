"""
PreCompact hook — injects current version/tool-count into compact instructions.
Claude Code runs this before every compaction. Output must be JSON with
"newCustomInstructions" key.
"""
import re
import json
import sys

try:
    src = open("Content/Python/UEFN_Toolbelt/__init__.py", encoding="utf-8").read()
    version  = re.search(r'__version__\s*=\s*["\']([^"\']+)', src).group(1)
    tools    = re.search(r'__tool_count__\s*=\s*(\d+)', src).group(1)
    cats     = re.search(r'__category_count__\s*=\s*(\d+)', src).group(1)
    instructions = (
        f"Current codebase state: version={version}, tool_count={tools}, "
        f"category_count={cats}. "
        "Preserve these exact numbers through compaction. "
        "Also preserve: any tool names added/modified this session, "
        "UEFN quirk numbers discovered, live test confirmations from UEFN log output, "
        "and full code for any new @register_tool functions."
    )
    print(json.dumps({"newCustomInstructions": instructions}))
except Exception as e:
    # Non-zero exit would block compaction — print empty instructions instead
    print(json.dumps({"newCustomInstructions": ""}))
    sys.exit(0)

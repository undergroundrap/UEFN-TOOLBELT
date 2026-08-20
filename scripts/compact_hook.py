"""
PreCompact hook — injects current version/tool-count into compact instructions.
Claude Code runs this before every compaction. Output must be JSON with
"newCustomInstructions" key.
"""
import json
import re
import sys

try:
    with open("Content/Python/UEFN_Toolbelt/__init__.py", encoding="utf-8") as _f:
        src = _f.read()
    version  = re.search(r'__version__\s*=\s*["\']([^"\']+)', src).group(1)  # type: ignore[union-attr]
    tools    = re.search(r'__tool_count__\s*=\s*(\d+)', src).group(1)  # type: ignore[union-attr]
    cats     = re.search(r'__category_count__\s*=\s*(\d+)', src).group(1)  # type: ignore[union-attr]
    instructions = (
        f"Current codebase state: version={version}, tool_count={tools}, "
        f"category_count={cats}. "
        "Preserve these exact numbers through compaction. "
        "Also preserve: any tool names added/modified this session, "
        "UEFN quirk numbers discovered, live test confirmations from UEFN log output, "
        "and full code for any new @register_tool functions."
    )
    print(json.dumps({"newCustomInstructions": instructions}))
except Exception:
    # Non-zero exit would block compaction — print empty instructions instead
    print(json.dumps({"newCustomInstructions": ""}))
    sys.exit(0)

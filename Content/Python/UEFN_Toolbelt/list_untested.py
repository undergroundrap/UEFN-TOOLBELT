"""
UEFN Toolbelt — Coverage Report
=================================
Prints which registered tools have no automated test coverage.
Run from any Python (outside UEFN is fine):

    python Content/Python/UEFN_Toolbelt/list_untested.py

Exit code 0 = all covered, 1 = gaps found (CI-friendly).
"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))           # …/UEFN_Toolbelt/
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(_ROOT)))  # repo root
_TESTS = os.path.join(_PROJECT, "tests")
_TOOLS = os.path.join(_ROOT, "tools")

# ── Collect all registered tool names ────────────────────────────────────────

all_tools: set[str] = set()
for fname in os.listdir(_TOOLS):
    if not fname.endswith(".py"):
        continue
    with open(os.path.join(_TOOLS, fname), "r", encoding="utf-8") as f:
        text = f.read()
    for name in re.findall(r'@register_tool\s*\(\s*name=[\'"]([^\'"]+)[\'"]', text):
        all_tools.add(name)

# ── Collect tool names referenced in test files ───────────────────────────────

covered_tools: set[str] = set()
test_files = [
    os.path.join(_TESTS, "smoke_test.py"),
    os.path.join(_TOOLS, "integration_test.py"),
]
for path in test_files:
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Direct run("tool_name") calls
    for name in re.findall(r'run\s*\(\s*[\'"]([^\'"]+)[\'"]', text):
        covered_tools.add(name)
    # String literals in list/tuple assignments (e.g. safe_tools_to_test = [...])
    for name in re.findall(r'[\'"]([a-z][a-z0-9_]{3,})[\'"]', text):
        if name in all_tools:
            covered_tools.add(name)

# ── Report ────────────────────────────────────────────────────────────────────

uncovered = sorted(all_tools - covered_tools)
covered_count = len(all_tools) - len(uncovered)
pct = 100 * covered_count / len(all_tools) if all_tools else 0

print(f"\n=== UEFN Toolbelt — Test Coverage Report ===")
print(f"  Total tools:    {len(all_tools)}")
print(f"  Covered:        {covered_count}  ({pct:.0f}%)")
print(f"  Uncovered:      {len(uncovered)}")

if uncovered:
    print(f"\n  Uncovered tools ({len(uncovered)}):")

    # Group by rough category via tool name prefix
    by_prefix: dict[str, list[str]] = {}
    for name in uncovered:
        prefix = name.split("_")[0]
        by_prefix.setdefault(prefix, []).append(name)

    for prefix in sorted(by_prefix):
        for name in by_prefix[prefix]:
            print(f"    {name}")

    print()
    print("  Add these to tests/smoke_test.py _safe_run calls or")
    print("  integration_test.py to close coverage gaps.")
    sys.exit(1)
else:
    print("\n  All tools covered.")
    sys.exit(0)

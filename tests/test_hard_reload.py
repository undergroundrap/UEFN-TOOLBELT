"""
tb.hard_reload() must leave the registry as full as a fresh start did.

It has now been wrong three times, each time in a way that LOOKED fine:

  1. Popped UEFN_Toolbelt itself and re-imported into a local name, so the
     caller's `tb` kept pointing at the old module and its old registry.
  2. Reported pkg.__tool_count__ — a constant — so the log read "362 tools"
     while the registry actually held 1.
  3. Cleared sys.modules but left the submodule ATTRIBUTES on the package.
     importlib.reload() re-executes __init__.py into the existing namespace
     without clearing it, so `from . import tools` found pkg.tools already set,
     skipped the import, and rebound the stale module. Nothing re-registered.

Every one of those needs a real reload to detect, so this runs in a subprocess:
reloading the package inside the test session would invalidate the module
references every other test holds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent

_SCRIPT = """
import sys
sys.path.insert(0, r"{tests}")
import conftest  # installs the fake `unreal` module and fixes sys.path

import UEFN_Toolbelt as tb
tb.register()
before = len(tb.registry)
before_id = id(tb)

result = tb.hard_reload(verbose=False)

after = len(tb.registry)
print("BEFORE", before)
print("AFTER", after)
print("TOOLS_IN_SYS_MODULES", "UEFN_Toolbelt.tools" in sys.modules)
print("SAME_MODULE_OBJECT", id(tb) == before_id)
print("REPORTED", result["tools"])
print("STATUS", result["status"])
print("EXPECTED", result["expected_tools"])
"""


def _run() -> dict[str, str]:
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(tests=str(TESTS))],
        capture_output=True, text=True, cwd=str(TESTS.parent),
    )
    assert proc.returncode == 0, f"reload crashed:\n{proc.stdout}\n{proc.stderr}"
    out = {}
    for line in proc.stdout.splitlines():
        if " " in line:
            k, _, v = line.partition(" ")
            out[k] = v
    return out


def test_hard_reload_keeps_every_tool_registered():
    r = _run()
    assert r["BEFORE"] == r["AFTER"], (
        f"reload lost tools: {r['BEFORE']} -> {r['AFTER']}. The submodule "
        f"attributes on the package were probably not cleared."
    )
    assert int(r["AFTER"]) > 1


def test_hard_reload_actually_reimports_the_tools_package():
    """The precise symptom of the attribute bug: sys.modules stays empty."""
    assert _run()["TOOLS_IN_SYS_MODULES"] == "True"


def test_hard_reload_preserves_the_callers_module_object():
    """`import UEFN_Toolbelt as tb` must still be the reloaded module."""
    assert _run()["SAME_MODULE_OBJECT"] == "True"


def test_hard_reload_reports_a_measured_count_not_a_constant():
    """It reported 362 while holding 1. The number has to be counted."""
    r = _run()
    assert r["REPORTED"] == r["AFTER"], "reported count is not the live count"
    assert r["STATUS"] == "ok"
    assert r["REPORTED"] == r["EXPECTED"]

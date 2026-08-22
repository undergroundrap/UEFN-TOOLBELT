"""Build status must reflect the LAST build in the log, not the best one.

Two bugs, both of the confident-wrong-answer kind:

1. `max(log_files, key=os.path.getmtime)` picked whichever .log was touched
   most recently. Saved/Logs holds UnrealRevisionControl.log, crash backups and
   others that are frequently newer than the editor log and have never
   contained a VerseBuild line, so status came back UNKNOWN for no visible
   reason.

2. The scan let any SUCCESS marker win permanently:

       if success: status = "SUCCESS"
       elif failed:
           if status != "SUCCESS":       # <- never downgrades
               status = "FAILED"

   A session log holds every build you have run. Once one went green, every
   later failure still reported SUCCESS. In the Phase 5 build-and-fix loop that
   tells the agent its broken code compiled, so it stops fixing.

The second one is the reason this file exists: it is invisible in a single-build
log and only appears on the second build of a session, which is exactly when
nobody is watching the status closely.
"""

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    """Import system_build as part of its package.

    It uses relative imports, so loading it by file path raises
    "attempted relative import with no known parent package". conftest.py
    already puts UEFN_Toolbelt on the path with a fake `unreal` installed,
    which is how the other tests here reach tool modules.
    """
    return importlib.import_module("UEFN_Toolbelt.tools.system_build")


SUCCESS = "LogSolaris: VerseBuild SUCCESS - build complete."
FAILED = "VerseBuild: FAILED - 3 errors."


def test_a_later_failure_beats_an_earlier_success():
    """The exact regression. Fails against the old 'any SUCCESS wins' logic."""
    mod = _load()
    assert mod._scan_build_status([SUCCESS, FAILED]) == "FAILED"


def test_a_later_success_beats_an_earlier_failure():
    mod = _load()
    assert mod._scan_build_status([FAILED, SUCCESS]) == "SUCCESS"


def test_no_markers_is_unknown_not_a_guess():
    mod = _load()
    assert mod._scan_build_status(["LogPython: hello", ""]) == "UNKNOWN"


def test_the_editor_log_is_preferred_over_the_newest_file():
    """Name beats mtime. The newest .log is often revision control, which has
    never held a VerseBuild line."""
    mod = _load()
    import os
    import tempfile
    import time

    with tempfile.TemporaryDirectory() as d:
        editor = os.path.join(d, "UnrealEditorFortnite.log")
        noise = os.path.join(d, "UnrealRevisionControl.log")
        Path(editor).write_text("x", encoding="utf-8")
        time.sleep(0.01)
        Path(noise).write_text("x", encoding="utf-8")   # newer on purpose

        assert os.path.getmtime(noise) >= os.path.getmtime(editor)
        assert mod._pick_build_log([noise, editor]) == editor
        # and with no editor log present it still returns something usable
        assert mod._pick_build_log([noise]) == noise


def test_no_call_site_blocks_the_downgrade():
    """The two tools scan status inline, in the same pass they collect errors,
    so they do not go through _scan_build_status. Testing the helper alone
    would leave the code that actually runs unguarded — this checks the source
    for the shape that caused the bug.
    """
    src = MODULE_SRC()
    assert 'build_status != "SUCCESS"' not in src, (
        "a call site is blocking the FAILED downgrade again — once any build in "
        "the session log goes green, every later failure will report SUCCESS"
    )
    # Non-vacuous: the detector must reject the original construct.
    old_shape = 'if build_status != "SUCCESS":\n    build_status = "FAILED"'
    assert 'build_status != "SUCCESS"' in old_shape


def MODULE_SRC() -> str:
    return (ROOT / "Content" / "Python" / "UEFN_Toolbelt" / "tools"
            / "system_build.py").read_text(encoding="utf-8")


def test_a_localised_editor_reports_unknown_and_that_is_deliberate():
    """Known limitation, pinned so it stays a decision rather than a surprise.

    The editor localises its build markers, so a non-English install gets
    UNKNOWN rather than SUCCESS or FAILED. Matching translated strings is only
    worth doing with markers verified against a real localised editor - guessing
    at them yields a checker that looks like it covers other locales and does
    not, which is worse than plainly not covering them.

    If someone adds locale support, this test should fail and be replaced with
    real coverage.
    """
    mod = _load()
    assert mod._scan_build_status(["VerseBuild: ERFOLGREICH"]) == "UNKNOWN"

"""
Pytest bootstrap for UEFN Toolbelt.
==============================================================================
The whole package does `import unreal`, a module that only exists inside the
UEFN editor process. Without it nothing is importable off-editor, which is why
this repo previously had no runnable tests.

This conftest installs a permissive stand-in for `unreal` into `sys.modules`
BEFORE any Toolbelt import, so modules whose logic is pure Python (the registry,
the config store, path helpers) can be unit-tested in CI.

Scope and honesty about it:
    This does NOT simulate the editor. Anything that depends on real `unreal.*`
    behaviour still has to be verified live per CLAUDE.md — see tests/smoke_test.py
    and `tb.run("toolbelt_integration_test")`. What it covers is the pure-Python
    contract layer that the other 350+ tools are built on top of.
"""

from __future__ import annotations

import atexit
import shutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT / "Content" / "Python"

# Sandbox that stands in for the UEFN project directory. Anything the Toolbelt
# writes at import/run time (activity_log.json, config.json, exports) lands here.
_SANDBOX = Path(tempfile.mkdtemp(prefix="uefn_toolbelt_tests_"))
atexit.register(shutil.rmtree, _SANDBOX, True)


class _FakePaths:
    """
    Real string-returning stand-in for `unreal.Paths`.

    This must NOT be a MagicMock. `core/activity_log.py` does
    `os.path.join(unreal.Paths.project_saved_dir(), ...)` followed by makedirs —
    with a mock, str() yields "<MagicMock name='unreal.Paths.project_saved_dir()'
    id='...'>" and the suite creates a literal `MagicMock/` directory tree in the
    repo. Returning real paths keeps all writes inside the sandbox.
    """

    def __getattr__(self, name: str):
        def _path_fn(*args, **kwargs) -> str:
            target = _SANDBOX / name
            target.mkdir(parents=True, exist_ok=True)
            return str(target) + "/"
        return _path_fn


def _install_fake_unreal() -> None:
    """Register a MagicMock-backed `unreal` module if the real one is absent."""
    try:
        import unreal  # noqa: F401  — real editor module; nothing to do
        return
    except ImportError:
        pass

    fake = types.ModuleType("unreal")

    # Attribute access returns a fresh MagicMock, so `unreal.AnythingAtAll(...)`,
    # `unreal.SomeSubsystem.method()`, and isinstance-free duck typing all work.
    class _AutoModule(types.ModuleType):
        def __getattr__(self, name: str):  # noqa: ANN401
            mock = MagicMock(name=f"unreal.{name}")
            setattr(self, name, mock)
            return mock

    fake.__class__ = _AutoModule

    # Logging funcs are called constantly; make them no-ops rather than mocks so
    # test output stays readable.
    fake.log = lambda *a, **k: None            # type: ignore[attr-defined]
    fake.log_warning = lambda *a, **k: None    # type: ignore[attr-defined]
    fake.log_error = lambda *a, **k: None      # type: ignore[attr-defined]

    # Anything that feeds a filesystem path must return a real str, not a mock.
    fake.Paths = _FakePaths()                  # type: ignore[attr-defined]

    sys.modules["unreal"] = fake


_install_fake_unreal()

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


@pytest.fixture
def fresh_registry():
    """A clean ToolRegistry instance, isolated from the module-level singleton."""
    from UEFN_Toolbelt.registry import ToolRegistry

    return ToolRegistry()


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT

"""
UEFN Toolbelt Installer
=======================
Run this once to install UEFN Toolbelt into any UEFN project.

    python install.py
    python install.py --project "C:/MyProjects/MyIsland"

What it does:
  1. Auto-detects the UE-embedded python.exe and installs PySide6 into it
  2. Copies Content/Python/UEFN_Toolbelt/ into your project's Content/Python/
  3. Creates init_unreal.py if one doesn't exist, or patches it if one does

After running:
  Open UEFN. The Toolbelt menu appears automatically.
  In the Python console: import UEFN_Toolbelt as tb; tb.smoke_test()
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = os.path.dirname(os.path.abspath(__file__))
TOOLBELT_SRC = os.path.join(REPO_ROOT, "Content", "Python", "UEFN_Toolbelt")
INIT_SRC     = os.path.join(REPO_ROOT, "init_unreal.py")

# The discovery loop that init_unreal.py needs — we patch this into existing files
_LOADER_MARKER = "# [UEFN_TOOLBELT_LOADER]"
_LOADER_BLOCK = """
# [UEFN_TOOLBELT_LOADER] — added by UEFN Toolbelt installer
import sys as _sys, os as _os, importlib as _importlib
# __file__ is Content/Python/init_unreal.py — its directory IS the Python dir.
# unreal.Paths.project_content_dir() returns the FortniteGame engine path in UEFN
# (Quirk #23) and cannot be used here.
_PYTHON_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _PYTHON_DIR not in _sys.path:
    _sys.path.insert(0, _PYTHON_DIR)
for _name in sorted(_os.listdir(_PYTHON_DIR)):
    _pkg = _os.path.join(_PYTHON_DIR, _name)
    if _os.path.isdir(_pkg) and _os.path.exists(_os.path.join(_pkg, "__init__.py")):
        try:
            _mod = _importlib.import_module(_name)
            if callable(getattr(_mod, "register", None)):
                _mod.register()
        except Exception as _e:
            __import__("unreal").log_error(f"[LOADER] Failed to load '{_name}': {_e}")
del _sys, _os, _importlib, _PYTHON_DIR, _name, _pkg, _mod
# [/UEFN_TOOLBELT_LOADER]
"""

# ── PySide6 auto-install ──────────────────────────────────────────────────────

_UE_PYTHON_SEARCH_ROOTS = [
    # Standard Epic Games Launcher installs
    r"C:\Program Files\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe",
    r"C:\Program Files (x86)\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe",
    # Game Pass / Xbox App installs
    r"C:\Program Files\Epic Games\UEFNFortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe",
    # Common custom install drives
    r"D:\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe",
    r"E:\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe",
]


_UE_PYTHON_SUFFIX = os.path.join("Engine", "Binaries", "ThirdParty", "Python3", "Win64", "python.exe")


def _find_ue_python() -> str | None:
    """
    Find the python.exe embedded in the Unreal Engine install.
    1. Try hardcoded common paths.
    2. Read Epic's LauncherInstalled.dat — authoritative list of all installs.
    3. Scan all drives with common subfolder patterns as a fallback.
    Returns the path string, or None if not found.
    """
    # 1. Hardcoded common paths
    for path in _UE_PYTHON_SEARCH_ROOTS:
        if os.path.exists(path):
            return path

    # 2. Epic Games Launcher manifest — most reliable, works with any custom install path
    if sys.platform == "win32":
        import json as _json
        manifest = os.path.join(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
            "Epic Games", "UnrealEngineLauncher", "LauncherInstalled.dat"
        )
        if os.path.exists(manifest):
            try:
                with open(manifest, encoding="utf-8") as f:
                    data = _json.load(f)
                for entry in data.get("InstallationList", []):
                    install_loc = entry.get("InstallLocation", "")
                    if install_loc:
                        candidate = os.path.join(install_loc, _UE_PYTHON_SUFFIX)
                        if os.path.exists(candidate):
                            return candidate
            except Exception:
                pass

    # 3. Scan all drive letters with common subfolder patterns
    if sys.platform == "win32":
        import string
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        for drive in drives:
            for base in ["Program Files", "Program Files (x86)", "Epic Games", "Games", "UEFN", ""]:
                for app in ["Fortnite", "FortniteGame", "UEFNFortnite", "EpicGames\\Fortnite"]:
                    candidate = os.path.join(drive, base, app, _UE_PYTHON_SUFFIX) if base else \
                                os.path.join(drive, app, _UE_PYTHON_SUFFIX)
                    if os.path.exists(candidate):
                        return candidate

    return None


def _ensure_pyside6() -> None:
    """
    Check if PySide6 is installed in the UE-embedded Python. Install it if not.
    Silently skips if the UE Python can't be found (e.g. not yet installed).
    """
    ue_python = _find_ue_python()
    if not ue_python:
        print("  ⚠  Could not find UE-embedded python.exe — skipping PySide6 install.")
        print("     If the dashboard is blank, install manually:")
        print('     "<UE_PATH>\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe" -m pip install PySide6')
        return

    print(f"  Found UE Python: {ue_python}")

    # Check if PySide6 is already installed
    check = subprocess.run(
        [ue_python, "-c", "import PySide6"],
        capture_output=True,
    )
    if check.returncode == 0:
        print("  ✓ PySide6 already installed — nothing to do.")
        return

    # Verify pip is available before attempting install
    pip_check = subprocess.run(
        [ue_python, "-m", "pip", "--version"],
        capture_output=True,
    )
    if pip_check.returncode != 0:
        print("  ✗ UE Python is missing pip — cannot auto-install PySide6.")
        print("     Install manually by opening a terminal and running:")
        print(f'     "{ue_python}" -m pip install PySide6')
        print("     (If pip is missing entirely, reinstall Fortnite via the Epic Launcher.)")
        return

    print("  Installing PySide6 into UE Python (this takes ~30 seconds)...")
    result = subprocess.run(
        [ue_python, "-m", "pip", "install", "PySide6", "--quiet"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  ✓ PySide6 installed successfully.")
    else:
        print("  ✗ PySide6 install failed. Install manually:")
        print(f'     "{ue_python}" -m pip install PySide6')
        if result.stderr.strip():
            print(f"     Error: {result.stderr.strip()}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_uefn_projects():
    """Best-effort scan of common UEFN project locations."""
    candidates = []
    roots = []

    if sys.platform == "win32":
        roots = [
            os.path.expanduser("~/Documents/Fortnite Projects"),  # UEFN default
            os.path.expanduser("~/Documents/Unreal Projects"),
            os.path.expanduser("~/Documents/UEFN"),
        ]
    else:
        roots = [
            os.path.expanduser("~/Documents/Fortnite Projects"),
            os.path.expanduser("~/Documents/Unreal Projects"),
            os.path.expanduser("~/UnrealProjects"),
        ]

    for root in roots:
        if os.path.isdir(root):
            try:
                entries = os.listdir(root)
            except (PermissionError, OSError):
                continue
            for name in entries:
                uproject = os.path.join(root, name, f"{name}.uproject")
                if os.path.exists(uproject):
                    candidates.append(os.path.join(root, name))

    return candidates


def _pick_project(explicit_path: str | None) -> str:
    if explicit_path:
        if not os.path.isdir(explicit_path):
            print(f"ERROR: Path does not exist: {explicit_path}")
            sys.exit(1)
        return os.path.abspath(explicit_path)

    candidates = _find_uefn_projects()

    if candidates:
        print("\nFound UEFN projects:")
        for i, c in enumerate(candidates):
            print(f"  [{i+1}] {c}")
        print(f"  [0] Enter path manually")
        choice = input("\nSelect project (number): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]

    path = input("Enter your UEFN project folder path: ").strip().strip('"')
    if not os.path.isdir(path):
        print(f"ERROR: Path does not exist: {path}")
        sys.exit(1)
    return os.path.abspath(path)


def _install_toolbelt(project_path: str):
    dest_python = os.path.join(project_path, "Content", "Python")
    dest_tb     = os.path.join(dest_python, "UEFN_Toolbelt")
    dest_init   = os.path.join(dest_python, "init_unreal.py")

    os.makedirs(dest_python, exist_ok=True)

    # ── Step 1: Copy the Toolbelt package ─────────────────────────────────────
    try:
        if os.path.exists(dest_tb):
            print(f"  Updating existing installation...")
            shutil.rmtree(dest_tb)
        shutil.copytree(TOOLBELT_SRC, dest_tb)
        print(f"  ✓ Copied UEFN_Toolbelt → {dest_tb}")
    except Exception as e:
        print(f"  ✗ Failed to copy Toolbelt: {e}")
        sys.exit(1)

    # ── Step 2: Handle init_unreal.py ─────────────────────────────────────────
    if not os.path.exists(dest_init):
        # Clean install — just copy the template
        shutil.copy2(INIT_SRC, dest_init)
        print(f"  ✓ Created init_unreal.py → {dest_init}")
    else:
        # Existing file — patch it if the loader block isn't already there
        with open(dest_init, "r", encoding="utf-8") as f:
            existing = f.read()

        if _LOADER_MARKER in existing:
            # Marker present — replace the old block with the current one so
            # future installs always update the loader (e.g. after a bug fix).
            import re as _re
            new_content = _re.sub(
                r"# \[UEFN_TOOLBELT_LOADER\].*?# \[/UEFN_TOOLBELT_LOADER\]",
                _LOADER_BLOCK.strip(),
                existing,
                flags=_re.DOTALL,
            )
            try:
                with open(dest_init, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"  ✓ Updated Toolbelt loader block in init_unreal.py")
            except Exception as e:
                print(f"  ✗ Failed to update init_unreal.py: {e}")
                sys.exit(1)
        else:
            try:
                with open(dest_init, "a", encoding="utf-8") as f:
                    f.write(_LOADER_BLOCK)
                print(f"  ✓ Patched existing init_unreal.py with Toolbelt loader block")
                print(f"    (Your original init_unreal.py content is unchanged above the patch)")
            except PermissionError:
                print(f"  ✗ init_unreal.py is read-only — could not patch it.")
                print(f"    Make it writable and re-run install.py, or manually append the loader block.")
                sys.exit(1)
            except Exception as e:
                print(f"  ✗ Failed to patch init_unreal.py: {e}")
                sys.exit(1)


def _print_next_steps(project_path: str):
    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Install complete.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
  1. Open your UEFN project
  2. The "Toolbelt ▾" menu appears in the top menu bar automatically
  3. Verify in the Python console:

       import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_smoke_test")

To write your own plugin:
  1. Create a .py file with a @register_tool decorated function
  2. Drop it in:
       [Project]/Saved/UEFN_Toolbelt/Custom_Plugins/
  3. It loads automatically on next start (no changes to Toolbelt needed)

To update Toolbelt later:
  git pull  (in this repo)
  python install.py --project "path/to/your/project"
""")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Install UEFN Toolbelt into a UEFN project."
    )
    parser.add_argument(
        "--project", "-p",
        metavar="PATH",
        help="Path to your UEFN project folder (optional — installer will prompt if omitted)",
    )
    args = parser.parse_args()

    print("\nUEFN Toolbelt Installer")
    print("═" * 40)

    # Step 0: PySide6 (dashboard UI dependency)
    print("\n[1/3] Checking PySide6...")
    _ensure_pyside6()

    # Step 1-2: Install into project
    print("\n[2/3] Selecting UEFN project...")
    project_path = _pick_project(args.project)
    print(f"\n[3/3] Installing into: {project_path}\n")

    _install_toolbelt(project_path)
    _print_next_steps(project_path)


if __name__ == "__main__":
    main()

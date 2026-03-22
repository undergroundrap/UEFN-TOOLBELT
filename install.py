"""
UEFN Toolbelt Installer
=======================
Run this once to install UEFN Toolbelt into any UEFN project.

    python install.py
    python install.py --project "C:/MyProjects/MyIsland"

What it does:
  1. Copies Content/Python/UEFN_Toolbelt/ into your project's Content/Python/
  2. Creates init_unreal.py if one doesn't exist, or patches it if one does
  3. Nothing else — no internet, no dependencies, no registry entries

After running:
  Open UEFN. The Toolbelt menu appears automatically.
  In the Python console: import UEFN_Toolbelt as tb; tb.smoke_test()
"""

import argparse
import os
import re
import shutil
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
_PYTHON_DIR = _os.path.join(__import__("unreal").Paths.project_content_dir(), "Python")
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
del _sys, _os, _importlib, _PYTHON_DIR
# [/UEFN_TOOLBELT_LOADER]
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_uefn_projects():
    """Best-effort scan of common UEFN project locations."""
    candidates = []
    roots = []

    if sys.platform == "win32":
        roots = [
            os.path.expanduser("~/Documents/Unreal Projects"),
            os.path.expanduser("~/Documents/UEFN"),
            "C:/Users/Public/Documents/Unreal Projects",
        ]
        # Also check all drive letters for a FortniteGame folder hint
    else:
        roots = [
            os.path.expanduser("~/Documents/Unreal Projects"),
            os.path.expanduser("~/UnrealProjects"),
        ]

    for root in roots:
        if os.path.isdir(root):
            for name in os.listdir(root):
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
    if os.path.exists(dest_tb):
        shutil.rmtree(dest_tb)
    shutil.copytree(TOOLBELT_SRC, dest_tb)
    print(f"  ✓ Copied UEFN_Toolbelt → {dest_tb}")

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
            print(f"  ✓ init_unreal.py already contains the Toolbelt loader — no changes needed")
        else:
            with open(dest_init, "a", encoding="utf-8") as f:
                f.write(_LOADER_BLOCK)
            print(f"  ✓ Patched existing init_unreal.py with Toolbelt loader block")
            print(f"    (Your original init_unreal.py content is unchanged above the patch)")


def _print_next_steps(project_path: str):
    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Install complete.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
  1. Open your UEFN project
  2. The "Toolbelt ▾" menu appears in the top menu bar automatically
  3. Verify in the Python console:

       import UEFN_Toolbelt as tb; tb.smoke_test()

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

    project_path = _pick_project(args.project)
    print(f"\nInstalling into: {project_path}\n")

    _install_toolbelt(project_path)
    _print_next_steps(project_path)


if __name__ == "__main__":
    main()

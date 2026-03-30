"""
UEFN TOOLBELT — mcp_server.py
=========================================
External FastMCP bridge that connects Claude Code to the UEFN editor.

This is the *outside-UEFN* side of the two-process MCP architecture:

    Claude Code  ←── stdio ──→  mcp_server.py (this file, external)
                                       │
                                  HTTP POST 127.0.0.1:8765
                                       │
                             UEFN editor process
                             └── Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py

Requirements:
    pip install mcp
    (Uses the standard 'mcp' package from Anthropic — same as Claude Code MCP ecosystem)

One-time setup:
    pip install mcp
    # Place this file anywhere accessible (project root is fine)

Claude Code config — add to .mcp.json in your project root:
    {
      "mcpServers": {
        "uefn-toolbelt": {
          "command": "python",
          "args": ["<ABSOLUTE_PATH_TO_THIS_FILE>"]
        }
      }
    }

Then in UEFN (Output Log or Toolbelt dashboard):
    import UEFN_Toolbelt as tb; tb.run("mcp_start")

After that, Claude Code has full control over UEFN — 343 tools, live actor data,
arbitrary Python execution, viewport control, and more.

What this exposes (beyond Kirch's original 22 tools):
    run_toolbelt_tool   — call any of the 247 registered toolbelt tools by name
    list_toolbelt_tools — list every available tool with category and description
    mcp_get_log         — read the last N lines of the MCP listener log ring

Author: Ocean Bennett
License: AGPL-3.0 with visible attribution requirement (see LICENSE)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# ─── Configuration ────────────────────────────────────────────────────────────

try:
    LISTENER_PORT = int(os.environ.get("UEFN_MCP_PORT", "8765"))
    if not (1 <= LISTENER_PORT <= 65535):
        raise ValueError(f"Port {LISTENER_PORT} out of range")
except ValueError:
    LISTENER_PORT = 8765
LISTENER_URL    = f"http://127.0.0.1:{LISTENER_PORT}"
VERSE_BOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "verse-book", "docs")

# Chapter topic → filename map for verse_book_chapter()
_VERSE_CHAPTERS: dict[str, str] = {
    "overview":       "00_overview.md",
    "expressions":    "01_expressions.md",
    "primitives":     "02_primitives.md",
    "types":          "02_primitives.md",
    "containers":     "03_containers.md",
    "arrays":         "03_containers.md",
    "maps":           "03_containers.md",
    "operators":      "04_operators.md",
    "mutability":     "05_mutability.md",
    "var":            "05_mutability.md",
    "functions":      "06_functions.md",
    "control":        "07_control.md",
    "if":             "07_control.md",
    "for":            "07_control.md",
    "failure":        "08_failure.md",
    "failable":       "08_failure.md",
    "decides":        "08_failure.md",
    "structs":        "09_structs_enums.md",
    "enums":          "09_structs_enums.md",
    "classes":        "10_classes_interfaces.md",
    "interfaces":     "10_classes_interfaces.md",
    "inheritance":    "10_classes_interfaces.md",
    "subtyping":      "11_types.md",
    "access":         "12_access.md",
    "public":         "12_access.md",
    "private":        "12_access.md",
    "effects":        "13_effects.md",
    "specifiers":     "13_effects.md",
    "computes":       "13_effects.md",
    "suspends":       "13_effects.md",
    "concurrency":    "14_concurrency.md",
    "async":          "14_concurrency.md",
    "spawn":          "14_concurrency.md",
    "race":           "14_concurrency.md",
    "sync":           "14_concurrency.md",
    "live_variables": "15_live_variables.md",
    "listenable":     "15_live_variables.md",
    "modules":        "16_modules.md",
    "using":          "16_modules.md",
    "persistable":    "17_persistable.md",
    "evolution":      "18_evolution.md",
    "syntax":         "VerseSyntaxValidation.md",
    "index":          "concept_index.md",
}
REQUEST_TIMEOUT        = 30.0
LONG_OPERATION_TIMEOUT = 120.0   # for tool runs that may take longer

# ─── HTTP client ──────────────────────────────────────────────────────────────


def _send(command: str, params: dict | None = None,
          timeout: float = REQUEST_TIMEOUT) -> dict:
    """
    Send a command to the UEFN listener and return the result dict.

    Raises:
        ConnectionError: Listener is not running or UEFN isn't open.
        RuntimeError:    Command failed inside UEFN.
        TimeoutError:    UEFN took too long to respond.
    """
    payload = json.dumps({"command": command, "params": params or {}}).encode()
    req = urllib.request.Request(
        LISTENER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        if "Connection refused" in str(e) or "No connection" in str(e):
            raise ConnectionError(
                "UEFN listener is not running.\n"
                "  Start it: In UEFN Output Log or Toolbelt dashboard → MCP: Start Listener\n"
                "  Or:       import UEFN_Toolbelt as tb; tb.run('mcp_start')"
            ) from e
        raise
    except Exception as e:
        if "timed out" in str(e).lower():
            raise TimeoutError(
                f"Command '{command}' timed out after {timeout}s.\n"
                "  The UEFN editor may be blocked. Try a shorter operation."
            ) from e
        raise

    if not body.get("success", False):
        err = body.get("error", "Unknown error")
        tb  = body.get("traceback", "")
        raise RuntimeError(f"UEFN error for '{command}': {err}\n{tb}".strip())

    return body.get("result", {})


def _j(obj: Any) -> str:
    """Pretty-print any object as JSON string."""
    return json.dumps(obj, indent=2)


# ─── FastMCP server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    "uefn-toolbelt",
    instructions=(
        "MCP server for the UEFN Toolbelt — the most comprehensive Python toolbelt "
        "for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).\n\n"
        "IMPORTANT: Start the listener in UEFN first:\n"
        "  import UEFN_Toolbelt as tb; tb.run('mcp_start')\n\n"
        "Key tools:\n"
        "  run_toolbelt_tool   — run ANY of the 247 registered toolbelt tools\n"
        "  execute_python      — run arbitrary Python inside UEFN with full unreal.*\n"
        "  list_toolbelt_tools — see every tool available\n"
        "  get_all_actors      — snapshot the level\n"
        "  get_selected_actors — what the user has selected right now\n\n"
        "Verse code generation (spec-accurate):\n"
        "  verse_book_search   — search the authoritative Verse spec by keyword\n"
        "  verse_book_chapter  — fetch a full spec chapter by topic\n"
        "  verse_book_update   — git pull the latest spec from upstream\n\n"
        "IMPORTANT for Verse codegen: always call verse_book_search or verse_book_chapter\n"
        "BEFORE writing Verse code to ensure syntax is spec-accurate.\n\n"
        "The execute_python tool pre-populates: unreal, actor_sub, asset_sub, level_sub, tb."
    ),
)

# ─── System ───────────────────────────────────────────────────────────────────


@mcp.tool()
def ping() -> str:
    """Check if the UEFN Toolbelt listener is running and get its status."""
    return _j(_send("ping"))


@mcp.tool()
def execute_python(code: str) -> str:
    """Execute arbitrary Python inside the UEFN editor on the main thread.

    Pre-populated globals:
        unreal      — the full unreal Python module (37K+ types)
        actor_sub   — EditorActorSubsystem
        asset_sub   — EditorAssetSubsystem
        level_sub   — LevelEditorSubsystem
        tb          — UEFN_Toolbelt package (tb.run('tool_name', **kwargs))

    Assign to `result` to return a value. Use print() for stdout.

    Examples:
        # Get world name
        result = unreal.EditorLevelLibrary.get_editor_world().get_name()

        # Count actors by class
        actors = actor_sub.get_all_level_actors()
        from collections import Counter
        result = dict(Counter(a.get_class().get_name() for a in actors))

        # Run a toolbelt tool programmatically
        tb.run('material_apply_preset', preset='chrome')
    """
    result = _send("execute_python", {"code": code}, timeout=LONG_OPERATION_TIMEOUT)
    parts = []
    if result.get("stdout"):
        parts.append(f"stdout:\n{result['stdout'].rstrip()}")
    if result.get("stderr"):
        parts.append(f"stderr:\n{result['stderr'].rstrip()}")
    if result.get("result") is not None:
        parts.append(f"result: {_j(result['result'])}")
    return "\n\n".join(parts) if parts else "(no output)"


@mcp.tool()
def mcp_get_log(last_n: int = 50) -> str:
    """Get the last N lines from the MCP listener's internal log ring."""
    result = _send("get_log", {"last_n": last_n})
    lines = result.get("lines", [])
    return "\n".join(lines) if lines else "(log is empty)"


# ─── Toolbelt bridge (the killer feature) ─────────────────────────────────────


@mcp.tool()
def run_toolbelt_tool(tool_name: str, kwargs: dict | None = None) -> str:
    """Run any registered UEFN Toolbelt tool by name.

    This is the single most powerful MCP tool — it exposes all 343 toolbelt tools
    to Claude Code through one command. Instead of writing custom execute_python
    code, just name the tool and pass its arguments as a dict.

    Args:
        tool_name: Registered tool name (e.g. 'material_apply_preset').
        kwargs:    Dict of keyword arguments for the tool (optional).

    Examples:
        run_toolbelt_tool("material_apply_preset", {"preset": "chrome"})
        run_toolbelt_tool("arena_generate", {"size": "large", "apply_team_colors": True})
        run_toolbelt_tool("scatter_hism", {"count": 200, "radius": 4000.0})
        run_toolbelt_tool("snapshot_save")
        run_toolbelt_tool("tag_add", {"key": "biome", "value": "desert"})
        run_toolbelt_tool("screenshot_focus_selection")
        run_toolbelt_tool("ref_full_report", {"scan_path": "/Game"})

    Use list_toolbelt_tools() first to discover available tool names.
    """
    result = _send(
        "run_tool",
        {"tool_name": tool_name, "kwargs": kwargs or {}},
        timeout=LONG_OPERATION_TIMEOUT,
    )
    return _j(result)


@mcp.tool()
def list_toolbelt_tools(category: str = "") -> str:
    """List all registered UEFN Toolbelt tools.

    Args:
        category: Optional filter (e.g. 'Materials', 'Procedural', 'MCP Bridge').
                  Leave empty to list everything.

    Returns JSON with tool name, category, description, and tags for every tool.
    Pass a name to run_toolbelt_tool() to execute it.
    """
    result = _send("list_tools", {"category": category})
    tools = result.get("tools", [])
    count = result.get("count", len(tools))
    return f"// {count} tools registered\n{_j(tools)}"


@mcp.tool()
def describe_toolbelt_tool(tool_name: str) -> str:
    """Get the full parameter schema for a single UEFN Toolbelt tool.

    Returns the tool's name, description, category, tags, and complete parameter
    signatures (type, required, default) — everything needed to call it correctly
    without loading the full tool manifest.

    Use this before calling run_toolbelt_tool() when you need to verify parameter
    names, types, or defaults for a specific tool.

    Args:
        tool_name: Registered tool name (e.g. 'scatter_hism', 'material_apply_preset').

    Examples:
        describe_toolbelt_tool("scatter_hism")
        describe_toolbelt_tool("verse_gen_game_skeleton")
        describe_toolbelt_tool("snapshot_save")
    """
    result = _send("describe_tool", {"tool_name": tool_name})
    return _j(result)


# ─── Actors ───────────────────────────────────────────────────────────────────


@mcp.tool()
def get_all_actors(class_filter: str = "") -> str:
    """List all actors in the current UEFN level.

    Args:
        class_filter: Optional class name to filter by (e.g. 'StaticMeshActor').
    """
    return _j(_send("get_all_actors", {"class_filter": class_filter}))


@mcp.tool()
def get_selected_actors() -> str:
    """Get the actors currently selected in the UEFN viewport."""
    return _j(_send("get_selected_actors"))


@mcp.tool()
def spawn_actor(
    asset_path: str = "",
    actor_class: str = "",
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
) -> str:
    """Spawn an actor in the current level.

    Provide asset_path OR actor_class (not both).

    Args:
        asset_path:  Content path (e.g. '/Engine/BasicShapes/Cube').
        actor_class: Unreal class name (e.g. 'PointLight', 'CameraActor').
        location:    [x, y, z] world coordinates. Defaults to origin.
        rotation:    [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if asset_path:  params["asset_path"]  = asset_path
    if actor_class: params["actor_class"] = actor_class
    if location:    params["location"]    = location
    if rotation:    params["rotation"]    = rotation
    return _j(_send("spawn_actor", params))


@mcp.tool()
def delete_actors(actor_paths: list[str]) -> str:
    """Delete actors by path name or label.

    Args:
        actor_paths: List of actor path names or labels to delete.
    """
    return _j(_send("delete_actors", {"actor_paths": actor_paths}))


@mcp.tool()
def set_actor_transform(
    actor_path: str,
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
    scale:    Optional[list[float]] = None,
) -> str:
    """Set an actor's transform (any combination of location, rotation, scale).

    Args:
        actor_path: Actor path name or label.
        location:   [x, y, z] world coordinates.
        rotation:   [pitch, yaw, roll] in degrees.
        scale:      [x, y, z] scale factors.
    """
    params: dict[str, Any] = {"actor_path": actor_path}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    if scale:    params["scale"]    = scale
    return _j(_send("set_actor_transform", params))


@mcp.tool()
def set_actor_property(actor_path: str, property_name: str, value: Any) -> str:
    """Set a single editor property on an actor.

    Args:
        actor_path:    Actor path name or label.
        property_name: Property to set (e.g. 'mobility', 'hidden_in_game').
        value:         New value (must be JSON-serializable and match the property type).
    """
    return _j(_send("set_actor_property",
                    {"actor_path": actor_path, "property_name": property_name,
                     "value": value}))


@mcp.tool()
def get_actor_properties(actor_path: str, properties: list[str]) -> str:
    """Read specific editor properties from an actor.

    Args:
        actor_path: Actor path name or label.
        properties: Property names to read (e.g. ['mobility', 'hidden_in_game']).
    """
    return _j(_send("get_actor_properties",
                    {"actor_path": actor_path, "properties": properties}))


# ─── Assets ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_assets(directory: str = "/Game/", recursive: bool = True,
                class_filter: str = "") -> str:
    """List assets in a Content Browser directory.

    Args:
        directory:    Content path (e.g. '/Game/', '/Game/Materials/').
        recursive:    Include subdirectories (default True).
        class_filter: Class name filter (e.g. 'Material', 'StaticMesh').
    """
    return _j(_send("list_assets", {"directory": directory,
                                    "recursive": recursive,
                                    "class_filter": class_filter}))


@mcp.tool()
def get_asset_info(asset_path: str) -> str:
    """Get detailed info (class, package, path) about an asset.

    Args:
        asset_path: Full asset path (e.g. '/Game/Materials/M_Base').
    """
    return _j(_send("get_asset_info", {"asset_path": asset_path}))


@mcp.tool()
def get_selected_assets() -> str:
    """Get assets currently selected in the Content Browser."""
    return _j(_send("get_selected_assets"))


@mcp.tool()
def rename_asset(old_path: str, new_path: str) -> str:
    """Rename or move an asset.

    Args:
        old_path: Current asset path.
        new_path: New destination path.
    """
    return _j(_send("rename_asset", {"old_path": old_path, "new_path": new_path}))


@mcp.tool()
def delete_asset(asset_path: str) -> str:
    """Delete an asset permanently.

    Args:
        asset_path: Full asset path to delete.
    """
    return _j(_send("delete_asset", {"asset_path": asset_path}))


@mcp.tool()
def duplicate_asset(source_path: str, dest_path: str) -> str:
    """Duplicate an asset to a new path.

    Args:
        source_path: Source asset path.
        dest_path:   Destination asset path.
    """
    return _j(_send("duplicate_asset", {"source_path": source_path,
                                        "dest_path": dest_path}))


@mcp.tool()
def does_asset_exist(asset_path: str) -> str:
    """Check if an asset exists at the given path.

    Args:
        asset_path: Asset path to check.
    """
    return _j(_send("does_asset_exist", {"asset_path": asset_path}))


@mcp.tool()
def save_asset(asset_path: str) -> str:
    """Save a modified asset to disk.

    Args:
        asset_path: Asset path to save.
    """
    return _j(_send("save_asset", {"asset_path": asset_path}))


@mcp.tool()
def import_asset(
    source_file: str,
    destination_path: str,
    replace_existing: bool = True,
    save: bool = True,
) -> str:
    """Import an external file (FBX, PNG, WAV, etc.) into the Content Browser.

    Args:
        source_file:      Absolute path to the file on disk.
        destination_path: Content Browser destination (e.g. '/Game/Imports').
        replace_existing: Overwrite if an asset at that path already exists.
        save:             Save the imported asset immediately.
    """
    return _j(_send("import_asset", {
        "source_file":       source_file,
        "destination_path":  destination_path,
        "replace_existing":  replace_existing,
        "save":              save,
    }))


@mcp.tool()
def search_assets(class_name: str = "", directory: str = "/Game/",
                  recursive: bool = True) -> str:
    """Search for assets using the Asset Registry.

    Args:
        class_name: Class name filter (e.g. 'Material', 'Texture2D', 'StaticMesh').
        directory:  Directory to search.
        recursive:  Include subdirectories.
    """
    return _j(_send("search_assets", {"class_name": class_name,
                                      "directory": directory,
                                      "recursive": recursive}))


# ─── Materials ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_material_instance(
    parent_path: str,
    instance_name: str,
    destination: str = "/Game/Materials",
    scalar_params: Optional[dict] = None,
    vector_params: Optional[dict] = None,
    texture_params: Optional[dict] = None,
) -> str:
    """Create a new MaterialInstanceConstant from a parent material.

    Args:
        parent_path:    Content path to the parent Material (e.g. '/Game/Materials/M_Master').
        instance_name:  Name for the new MI asset (e.g. 'MI_TeamRed').
        destination:    Content Browser destination folder.
        scalar_params:  {param_name: float} — e.g. {"Roughness": 0.2, "Metallic": 0.9}
        vector_params:  {param_name: [r,g,b,a]} — e.g. {"BaseColor": [1.0, 0.1, 0.1, 1.0]}
        texture_params: {param_name: asset_path} — e.g. {"DiffuseTex": "/Game/T_Rock"}
    """
    return _j(_send("create_material_instance", {
        "parent_path":    parent_path,
        "instance_name":  instance_name,
        "destination":    destination,
        "scalar_params":  scalar_params or {},
        "vector_params":  vector_params or {},
        "texture_params": texture_params or {},
    }))


@mcp.tool()
def batch_exec(commands: list[dict]) -> str:
    """Execute multiple bridge commands in a single UEFN editor tick.

    Faster than sending commands one-by-one for multi-step sequences.
    Each entry: {"command": "name", "params": {...}}

    Example:
        batch_exec([
            {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
            {"command": "run_tool", "params": {"tool_name": "bulk_align",
                                               "kwargs": {"axis": "Z"}}},
            {"command": "save_current_level", "params": {}},
        ])
    """
    return _j(_send("batch_exec", {"commands": commands}, timeout=120.0))


@mcp.tool()
def undo() -> str:
    """Undo the last action in the UEFN editor."""
    return _j(_send("undo"))


@mcp.tool()
def redo() -> str:
    """Redo the last undone action in the UEFN editor."""
    return _j(_send("redo"))


@mcp.tool()
def get_history(tail: int = 30) -> str:
    """Get recent command history with per-command timing (elapsed_ms)."""
    return _j(_send("history", {"tail": tail}))


# ─── Level ────────────────────────────────────────────────────────────────────


@mcp.tool()
def save_current_level() -> str:
    """Save the current level to disk."""
    return _j(_send("save_current_level"))


@mcp.tool()
def get_level_info() -> str:
    """Get info about the current level: world name and actor count."""
    return _j(_send("get_level_info"))


# ─── Viewport ─────────────────────────────────────────────────────────────────


@mcp.tool()
def get_viewport_camera() -> str:
    """Get the current editor viewport camera location and rotation."""
    return _j(_send("get_viewport_camera"))


@mcp.tool()
def set_viewport_camera(
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
) -> str:
    """Move the editor viewport camera.

    Args:
        location: [x, y, z] world coordinates.
        rotation: [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    return _j(_send("set_viewport_camera", params))


# ─── Verse Book (spec-aware code generation) ──────────────────────────────────


def _verse_book_missing() -> str:
    return (
        "verse-book not found at expected path.\n"
        "Fix: cd to the project root and run:\n"
        "  git clone https://github.com/verselang/book.git verse-book"
    )


@mcp.tool()
def verse_book_search(query: str, context_lines: int = 8) -> str:
    """Search the authoritative Verse language spec for a keyword or concept.

    Always call this before writing Verse code to verify syntax.
    Returns matching sections with surrounding context from all spec chapters.

    Args:
        query:         Keyword, specifier, or concept to look up
                       (e.g. 'suspends', 'editable', 'creative_device', 'race',
                       'Subscribe', 'map', 'option', 'interface').
        context_lines: Lines of context around each match (default 8).

    Examples:
        verse_book_search("suspends")          # effect specifier syntax
        verse_book_search("@editable")         # device property declarations
        verse_book_search("race block")        # concurrency race pattern
        verse_book_search("Subscribe")         # event subscription pattern
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for fname in sorted(os.listdir(VERSE_BOOK_PATH)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(VERSE_BOOK_PATH, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        i = 0
        while i < len(lines):
            if pattern.search(lines[i]):
                start = max(0, i - context_lines)
                end   = min(len(lines), i + context_lines + 1)
                snippet = "".join(lines[start:end])
                results.append(f"### {fname} — line {i + 1}\n{snippet}")
                i = end  # skip past this match block
            else:
                i += 1

    if not results:
        return f"No matches for '{query}' in the Verse spec."

    capped = results[:12]
    header = f"// {len(results)} match(es) for '{query}' — showing {len(capped)}\n\n"
    return header + "\n---\n".join(capped)


@mcp.tool()
def verse_book_chapter(topic: str) -> str:
    """Fetch a complete chapter from the Verse language spec by topic.

    Use when you need full coverage of a language area before generating code.
    Chapters are pulled from the live verse-book clone — always current.

    Args:
        topic: Topic name. Supported values:
               overview, expressions, primitives, containers, operators,
               mutability, functions, control, failure, structs, enums,
               classes, interfaces, types, access, effects, concurrency,
               async, live_variables, modules, persistable, evolution,
               syntax, index.

    Examples:
        verse_book_chapter("concurrency")   # async/suspends/race/sync
        verse_book_chapter("classes")       # class/interface/inheritance
        verse_book_chapter("failure")       # failable expressions, decides
        verse_book_chapter("effects")       # effect specifiers: computes/reads/writes
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    topic_key = topic.lower().replace(" ", "_").replace("-", "_")
    fname = _VERSE_CHAPTERS.get(topic_key)

    if fname is None:
        # Fuzzy fallback — partial match
        for key, f in _VERSE_CHAPTERS.items():
            if topic_key in key or key in topic_key:
                fname = f
                break

    if fname is None:
        available = sorted(set(_VERSE_CHAPTERS.keys()))
        return f"Unknown topic '{topic}'.\nAvailable topics: {available}"

    fpath = os.path.join(VERSE_BOOK_PATH, fname)
    try:
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        return f"// {fname}  ({len(content.splitlines())} lines)\n\n{content}"
    except Exception as e:
        return f"Error reading {fname}: {e}"


@mcp.tool()
def verse_book_update() -> str:
    """Pull the latest Verse spec from upstream (git pull on verse-book/).

    Run this when Epic releases Verse language updates to stay current.
    Returns the git output showing what changed.
    """
    book_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verse-book")
    if not os.path.isdir(os.path.join(book_root, ".git")):
        return _verse_book_missing()
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=book_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return f"// git pull — verse-book\n{output}"
    except subprocess.TimeoutExpired:
        return "git pull timed out after 30s."
    except Exception as e:
        return f"git pull failed: {e}"


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Allow --port override: python mcp_server.py --port 8766
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--port" and i < len(sys.argv) - 1:
            LISTENER_PORT = int(sys.argv[i + 1])
            LISTENER_URL  = f"http://127.0.0.1:{LISTENER_PORT}"

    mcp.run()

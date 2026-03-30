"""
UEFN TOOLBELT — mcp_bridge.py
=========================================
HTTP listener that exposes the UEFN editor to external processes
(Claude Code, scripts, CI pipelines) via a simple JSON-over-HTTP protocol.

Architecture:
    Claude Code  <-- stdio -->  mcp_server.py (external)
                                      |
                                   HTTP POST 127.0.0.1:8765
                                      |
                          UEFN editor process (this file)
                          ├── HTTP daemon thread (receives commands)
                          ├── queue.Queue (cross-thread handoff)
                          └── register_slate_post_tick_callback
                              (drains queue on main thread, calls unreal.*)

ATTRIBUTION:
    Concept and queue+tick architecture inspired by Kirch's uefn_listener.py:
      GitHub: https://github.com/KirChuvakov/uefn-mcp-server
      Twitter/X: https://x.com/KirchCreator
    Full credit to Kirch for pioneering the MCP bridge pattern for UEFN Python
    and validating the queue + Slate tick approach as the correct threading model.
    This implementation is an independent rewrite extended for the Toolbelt stack.

Why the queue + tick pattern:
    All unreal.* calls must happen on the editor's main thread.
    The HTTP server runs on a daemon thread. Commands are queued and
    dispatched to the main thread on every editor tick — the same approach
    pioneered by Kirch's uefn_listener.py (March 2026).

What's new vs Kirch's original:
    • run_tool command — call any registered UEFN Toolbelt tool by name,
      passing kwargs as JSON. Exposes all 355 toolbelt tools to any MCP client.
    • All 32 commands: Kirch's originals (system, actors, assets, level,
      viewport) + set_actor_property, import_asset, run_tool, describe_tool, and more.
    • Toolbelt-aware: pre-populated globals in execute_python include `tb`.
    • start / stop / restart / status exposed as @register_tool entries
      so the dashboard can control the bridge without touching the REPL.

Usage:
    # From the Toolbelt dashboard or REPL:
    import UEFN_Toolbelt as tb
    tb.run("mcp_start")        # start the HTTP listener
    tb.run("mcp_status")       # check port / running state
    tb.run("mcp_stop")         # stop the listener

    # From external Claude Code (after mcp_server.py is configured):
    "List all actors in the level"
    "Apply neon preset to all selected actors"
    "Run the scatter_hism tool with 200 props in a 4000cm radius"

External setup (one-time):
    pip install mcp
    # Add mcp_server.py path to .mcp.json or ~/.claude/settings.json

Port range:
    Auto-detects a free port in 8765-8770.
    The bound port is printed to the Output Log on start.
"""

from __future__ import annotations

import io
import json
import queue
import socket
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional

import unreal

from UEFN_Toolbelt.registry import register_tool

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_PORT       = 8765
MAX_PORT           = 8770
TICK_BATCH_LIMIT   = 5
HTTP_TIMEOUT_SEC   = 30.0
POLL_INTERVAL_SEC  = 0.02
STALE_CLEANUP_SEC  = 60.0
LOG_RING_SIZE      = 200
HISTORY_CAP        = 500

# ─── State ────────────────────────────────────────────────────────────────────

_server:         Optional[HTTPServer]       = None
_server_thread:  Optional[threading.Thread] = None
_tick_handle:    Optional[object]           = None
_bound_port:     int                        = 0
_start_time:     float                      = 0.0
_dispatch_mode:  str                        = "tick"   # "tick" or "direct"
_tick_health:    int                        = 0        # incremented each tick

_command_queue   = queue.Queue()
_responses:      Dict[str, dict]            = {}
_responses_lock  = threading.Lock()
_history:        deque                      = deque(maxlen=HISTORY_CAP)
_request_counter = 0

_log_ring: deque = deque(maxlen=LOG_RING_SIZE)

# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(msg: str, level: str = "info") -> None:
    entry = f"[MCP] {msg}"
    _log_ring.append(entry)
    if level == "error":
        unreal.log_error(entry)
    elif level == "warning":
        unreal.log_warning(entry)
    else:
        unreal.log(entry)


# ─── Serialization ────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Convert unreal objects to JSON-serializable Python types."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, unreal.Vector):
        return {"x": obj.x, "y": obj.y, "z": obj.z}
    if isinstance(obj, unreal.Rotator):
        return {"pitch": obj.pitch, "yaw": obj.yaw, "roll": obj.roll}
    if isinstance(obj, unreal.Vector2D):
        return {"x": obj.x, "y": obj.y}
    if isinstance(obj, unreal.LinearColor):
        return {"r": obj.r, "g": obj.g, "b": obj.b, "a": obj.a}
    if isinstance(obj, unreal.Color):
        return {"r": obj.r, "g": obj.g, "b": obj.b, "a": obj.a}
    if isinstance(obj, unreal.Transform):
        return {
            "location": _serialize(obj.translation),
            "rotation": _serialize(obj.rotation.rotator()),
            "scale":    _serialize(obj.scale3d),
        }
    if isinstance(obj, unreal.AssetData):
        try:
            cls = str(obj.asset_class_path.asset_name)
        except Exception:
            cls = str(getattr(obj, "asset_class", ""))
        try:
            opath = str(obj.get_export_text_name())
        except Exception:
            opath = str(getattr(obj, "object_path", ""))
        return {
            "asset_name":   str(obj.asset_name),
            "asset_class":  cls,
            "package_name": str(obj.package_name),
            "package_path": str(obj.package_path),
            "object_path":  opath,
        }
    if hasattr(obj, "get_path_name"):
        return str(obj.get_path_name())
    if hasattr(obj, "get_name"):
        return str(obj.get_name())
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _serialize_actor(actor: unreal.Actor) -> dict:
    return {
        "name":     actor.get_name(),
        "label":    actor.get_actor_label(),
        "class":    actor.get_class().get_name(),
        "path":     actor.get_path_name(),
        "location": _serialize(actor.get_actor_location()),
        "rotation": _serialize(actor.get_actor_rotation()),
        "scale":    _serialize(actor.get_actor_scale3d()),
    }


# ─── Command registry ─────────────────────────────────────────────────────────

_HANDLERS: Dict[str, Callable] = {}


def _cmd(name: str):
    def decorator(fn: Callable):
        _HANDLERS[name] = fn
        return fn
    return decorator


def _dispatch(command: str, params: dict) -> dict:
    handler = _HANDLERS.get(command)
    if handler is None:
        raise ValueError(
            f"Unknown command: {command!r}. "
            f"Available: {sorted(_HANDLERS.keys())}"
        )
    return handler(**params)


# ─── System commands ──────────────────────────────────────────────────────────

@_cmd("ping")
def _c_ping() -> dict:
    return {
        "status":         "ok",
        "app":            "UEFN Toolbelt MCP Bridge",
        "python_version": sys.version,
        "port":           _bound_port,
        "uptime_s":       round(time.time() - _start_time, 1) if _start_time else 0,
        "timestamp":      time.time(),
        "commands":       sorted(_HANDLERS.keys()),
    }


@_cmd("get_log")
def _c_get_log(last_n: int = 50) -> dict:
    return {"lines": _log_ring[-last_n:]}


@_cmd("execute_python")
def _c_execute_python(code: str) -> dict:
    """
    Execute arbitrary Python code on the main thread.
    Assign to `result` to return a value.
    Pre-populated globals: unreal, actor_sub, asset_sub, level_sub, tb.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr

    globs: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "unreal":       unreal,
        "result":       None,
    }
    # Subsystems
    for attr, cls_name in [
        ("actor_sub", "EditorActorSubsystem"),
        ("asset_sub", "EditorAssetSubsystem"),
        ("level_sub", "LevelEditorSubsystem"),
    ]:
        try:
            globs[attr] = unreal.get_editor_subsystem(getattr(unreal, cls_name))
        except Exception:
            pass
    # Toolbelt shortcut
    try:
        import UEFN_Toolbelt as _tb
        globs["tb"] = _tb
    except Exception:
        pass

    try:
        sys.stdout, sys.stderr = stdout_buf, stderr_buf
        exec(code, globs)
    except Exception:
        traceback.print_exc(file=stderr_buf)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    return {
        "result": _serialize(globs.get("result")),
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
    }


@_cmd("run_tool")
def _c_run_tool(tool_name: str, kwargs: dict | None = None) -> dict:
    """
    Run any registered UEFN Toolbelt tool by name.
    This exposes all 355 toolbelt tools to any MCP client in one command.

    Args:
        tool_name: The registered tool name (e.g. "material_apply_preset").
        kwargs:    Dict of keyword arguments forwarded to the tool function.

    Example:
        {"command": "run_tool",
         "params":  {"tool_name": "material_apply_preset",
                     "kwargs":    {"preset": "chrome"}}}
    """
    import UEFN_Toolbelt as _tb
    kw = kwargs or {}
    result = _tb.registry.execute(tool_name, **kw)
    return {"tool": tool_name, "kwargs": kw, "status": "executed",
            "result": _serialize(result)}


@_cmd("list_tools")
def _c_list_tools(category: str = "") -> dict:
    """List all registered UEFN Toolbelt tools, optionally filtered by category."""
    import UEFN_Toolbelt as _tb
    tools = _tb.registry.list_tools(category=category or None)
    return {"tools": tools, "count": len(tools)}


@_cmd("describe_tool")
def _c_describe_tool(tool_name: str) -> dict:
    """
    Return the full manifest entry for a single tool — name, description,
    category, tags, and complete parameter signatures.

    Useful for AI agents that need to know a tool's exact contract before
    calling it, without loading the full tool_manifest.json.

    Args:
        tool_name: The registered tool name (e.g. "scatter_hism").

    Example:
        {"command": "describe_tool", "params": {"tool_name": "scatter_hism"}}
    """
    import UEFN_Toolbelt as _tb
    manifest = _tb.registry.to_manifest()
    if tool_name not in manifest:
        return {"status": "error", "error": f"No tool named '{tool_name}'"}
    return {"status": "ok", "tool": manifest[tool_name]}


@_cmd("batch_exec")
def _c_batch_exec(commands: List[dict]) -> dict:
    """
    Execute multiple commands in sequence within a single editor tick.
    Faster than sending commands one-by-one for multi-step AI agent tasks.

    Args:
        commands: List of {"command": "name", "params": {...}} dicts.

    Example:
        {"command": "batch_exec", "params": {"commands": [
            {"command": "run_tool",
             "params": {"tool_name": "snapshot_save"}},
            {"command": "run_tool",
             "params": {"tool_name": "bulk_align", "kwargs": {"axis": "Z"}}},
            {"command": "save_current_level", "params": {}},
        ]}}
    """
    results = []
    for i, item in enumerate(commands):
        name   = item.get("command", "")
        params = item.get("params", {})
        try:
            result = _dispatch(name, params)
            results.append({"index": i, "command": name, "success": True, "result": result})
        except Exception as e:
            results.append({"index": i, "command": name, "success": False, "error": str(e)})
    return {"results": results, "count": len(results)}


@_cmd("undo")
def _c_undo() -> dict:
    """Undo the last editor action via the transaction system."""
    try:
        unreal.SystemLibrary.execute_console_command(None, "TRANSACTION UNDO")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@_cmd("redo")
def _c_redo() -> dict:
    """Redo the last undone action."""
    try:
        unreal.SystemLibrary.execute_console_command(None, "TRANSACTION REDO")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@_cmd("history")
def _c_history(tail: int = 30) -> dict:
    """Return recent command history with per-command timing."""
    return {"entries": _history[-tail:], "total": len(_history)}


# ─── Actor commands ───────────────────────────────────────────────────────────

@_cmd("get_all_actors")
def _c_get_all_actors(class_filter: str = "") -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = sub.get_all_level_actors()
    if class_filter:
        actors = [a for a in actors if a.get_class().get_name() == class_filter]
    return {"actors": [_serialize_actor(a) for a in actors], "count": len(actors)}


@_cmd("get_selected_actors")
def _c_get_selected_actors() -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = sub.get_selected_level_actors()
    return {"actors": [_serialize_actor(a) for a in actors], "count": len(actors)}


@_cmd("spawn_actor")
def _c_spawn_actor(
    asset_path: str = "",
    actor_class: str = "",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    label: str = "",
) -> dict:
    loc = unreal.Vector(*location) if location else unreal.Vector(0, 0, 0)
    rot = unreal.Rotator(*rotation) if rotation else unreal.Rotator(0, 0, 0)

    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if asset_path:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            raise ValueError(f"Asset not found: {asset_path}")
        actor = sub.spawn_actor_from_object(asset, loc, rot)
    elif actor_class:
        cls = getattr(unreal, actor_class, None)
        if cls is None:
            raise ValueError(f"Class not found: {actor_class}")
        actor = sub.spawn_actor_from_class(cls, loc, rot)
    else:
        raise ValueError("Provide either asset_path or actor_class")

    if actor is None:
        raise RuntimeError("Failed to spawn actor")
    if label:
        actor.set_actor_label(label)
    return {"actor": _serialize_actor(actor)}


@_cmd("delete_actors")
def _c_delete_actors(actor_paths: List[str]) -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = sub.get_all_level_actors()
    deleted = []
    for path in actor_paths:
        for actor in all_actors:
            if actor.get_path_name() == path or actor.get_actor_label() == path:
                sub.destroy_actor(actor)
                deleted.append(path)
                break
    return {"deleted": deleted, "count": len(deleted)}


@_cmd("set_actor_transform")
def _c_set_actor_transform(
    actor_path: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    target = next(
        (a for a in sub.get_all_level_actors()
         if a.get_path_name() == actor_path or a.get_actor_label() == actor_path),
        None,
    )
    if target is None:
        raise ValueError(f"Actor not found: {actor_path}")
    if location is not None:
        target.set_actor_location(unreal.Vector(*location), False, False)
    if rotation is not None:
        target.set_actor_rotation(unreal.Rotator(*rotation), False)
    if scale is not None:
        target.set_actor_scale3d(unreal.Vector(*scale))
    return {"actor": _serialize_actor(target)}


@_cmd("set_actor_property")
def _c_set_actor_property(actor_path: str, property_name: str, value: Any) -> dict:
    """Set a single editor property on an actor by path or label."""
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    target = next(
        (a for a in sub.get_all_level_actors()
         if a.get_path_name() == actor_path or a.get_actor_label() == actor_path),
        None,
    )
    if target is None:
        raise ValueError(f"Actor not found: {actor_path}")
    target.set_editor_property(property_name, value)
    return {"actor_path": actor_path, "property": property_name,
            "value": _serialize(value)}


@_cmd("get_actor_properties")
def _c_get_actor_properties(actor_path: str, properties: List[str]) -> dict:
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    target = next(
        (a for a in sub.get_all_level_actors()
         if a.get_path_name() == actor_path or a.get_actor_label() == actor_path),
        None,
    )
    if target is None:
        raise ValueError(f"Actor not found: {actor_path}")
    result = {}
    for prop in properties:
        try:
            result[prop] = _serialize(target.get_editor_property(prop))
        except Exception as e:
            result[prop] = f"<error: {e}>"
    return {"actor_path": actor_path, "properties": result}


# ─── Asset commands ───────────────────────────────────────────────────────────

@_cmd("list_assets")
def _c_list_assets(directory: str = "/Game/", recursive: bool = True,
                    class_filter: str = "") -> dict:
    assets = unreal.EditorAssetLibrary.list_assets(directory, recursive=recursive)
    if class_filter:
        filtered = []
        for path in assets:
            data = unreal.EditorAssetLibrary.find_asset_data(path)
            if data:
                try:
                    cls = str(data.asset_class_path.asset_name)
                except Exception:
                    cls = str(getattr(data, "asset_class", ""))
                if cls == class_filter:
                    filtered.append(str(path))
        assets = filtered
    else:
        assets = [str(a) for a in assets]
    return {"assets": assets, "count": len(assets)}


@_cmd("get_asset_info")
def _c_get_asset_info(asset_path: str) -> dict:
    data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
    if data is None:
        raise ValueError(f"Asset not found: {asset_path}")
    return {"asset": _serialize(data)}


@_cmd("get_selected_assets")
def _c_get_selected_assets() -> dict:
    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    return {"assets": [_serialize(a) for a in selected], "count": len(selected)}


@_cmd("rename_asset")
def _c_rename_asset(old_path: str, new_path: str) -> dict:
    success = unreal.EditorAssetLibrary.rename_asset(old_path, new_path)
    return {"success": success, "old_path": old_path, "new_path": new_path}


@_cmd("delete_asset")
def _c_delete_asset(asset_path: str) -> dict:
    success = unreal.EditorAssetLibrary.delete_asset(asset_path)
    return {"success": success, "asset_path": asset_path}


@_cmd("duplicate_asset")
def _c_duplicate_asset(source_path: str, dest_path: str) -> dict:
    result = unreal.EditorAssetLibrary.duplicate_asset(source_path, dest_path)
    return {"success": result is not None, "source": source_path, "dest": dest_path}


@_cmd("does_asset_exist")
def _c_does_asset_exist(asset_path: str) -> dict:
    exists = unreal.EditorAssetLibrary.does_asset_exist(asset_path)
    return {"exists": exists, "asset_path": asset_path}


@_cmd("save_asset")
def _c_save_asset(asset_path: str) -> dict:
    success = unreal.EditorAssetLibrary.save_asset(asset_path)
    return {"success": success, "asset_path": asset_path}


@_cmd("import_asset")
def _c_import_asset(
    source_file: str,
    destination_path: str,
    replace_existing: bool = True,
    automated: bool = True,
    save: bool = True,
) -> dict:
    """Import an external file (FBX, PNG, etc.) into the Content Browser."""
    task = unreal.AssetImportTask()
    task.filename = source_file
    task.destination_path = destination_path
    task.replace_existing = replace_existing
    task.automated = automated
    task.save = save
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = ([str(p) for p in task.imported_object_paths]
                if hasattr(task, "imported_object_paths") else [])
    return {"imported": imported, "count": len(imported), "source": source_file}


@_cmd("search_assets")
def _c_search_assets(class_name: str = "", directory: str = "/Game/",
                      recursive: bool = True) -> dict:
    reg    = unreal.AssetRegistryHelpers.get_asset_registry()
    filt   = unreal.ARFilter()
    if directory:
        filt.package_paths = [directory]
    filt.recursive_paths = recursive
    if class_name:
        try:
            filt.class_names = [class_name]
        except Exception:
            pass
    results = reg.get_assets(filt)
    return {"assets": [_serialize(a) for a in results], "count": len(results)}


# ─── Material commands ────────────────────────────────────────────────────────

@_cmd("create_material_instance")
def _c_create_material_instance(
    parent_path: str,
    instance_name: str,
    destination: str = "/Game/Materials",
    scalar_params: Optional[Dict[str, float]] = None,
    vector_params: Optional[Dict[str, List[float]]] = None,
    texture_params: Optional[Dict[str, str]] = None,
) -> dict:
    """
    Create a new MaterialInstanceConstant from a parent material.

    Args:
        parent_path:   Content path to the parent Material.
        instance_name: Name for the new MI asset.
        destination:   Content Browser destination folder.
        scalar_params: {param_name: float_value} — e.g. {"Roughness": 0.2}
        vector_params: {param_name: [r,g,b,a]} — e.g. {"BaseColor": [1,0,0,1]}
        texture_params:{param_name: asset_path} — e.g. {"DiffuseTex": "/Game/T_Rock"}

    Example:
        {"command": "create_material_instance", "params": {
            "parent_path": "/Game/Materials/M_Master",
            "instance_name": "MI_TeamRed",
            "destination": "/Game/Materials/Instances",
            "scalar_params": {"Roughness": 0.15, "Metallic": 0.9},
            "vector_params": {"BaseColor": [1.0, 0.05, 0.05, 1.0]}
        }}
    """
    tools   = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialInstanceConstantFactoryNew()
    mi      = tools.create_asset(instance_name, destination,
                                 unreal.MaterialInstanceConstant, factory)
    if not mi:
        raise RuntimeError(f"Failed to create material instance '{instance_name}'")

    parent = unreal.EditorAssetLibrary.load_asset(parent_path)
    if parent:
        mi.set_editor_property("parent", parent)

    if scalar_params:
        for k, v in scalar_params.items():
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                mi, k, float(v))
    if vector_params:
        for k, v in vector_params.items():
            col = (unreal.LinearColor(*v) if len(v) == 4
                   else unreal.LinearColor(v[0], v[1], v[2], 1.0))
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
                mi, k, col)
    if texture_params:
        for k, v in texture_params.items():
            tex = unreal.EditorAssetLibrary.load_asset(v)
            if tex:
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                    mi, k, tex)

    unreal.MaterialEditingLibrary.update_material_instance(mi)
    return {"path": str(mi.get_path_name()), "name": instance_name}


# ─── Level commands ───────────────────────────────────────────────────────────

@_cmd("save_current_level")
def _c_save_current_level() -> dict:
    success = unreal.EditorLevelLibrary.save_current_level()
    return {"success": success}


@_cmd("get_level_info")
def _c_get_level_info() -> dict:
    world  = unreal.EditorLevelLibrary.get_editor_world()
    sub    = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = sub.get_all_level_actors()
    return {
        "world_name":  world.get_name() if world else "None",
        "actor_count": len(actors),
    }


# ─── Viewport commands ────────────────────────────────────────────────────────

@_cmd("get_viewport_camera")
def _c_get_viewport_camera() -> dict:
    loc, rot = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
    return {"location": _serialize(loc), "rotation": _serialize(rot)}


@_cmd("set_viewport_camera")
def _c_set_viewport_camera(
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
) -> dict:
    cur_loc, cur_rot = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
    loc = unreal.Vector(*location) if location else cur_loc
    rot = unreal.Rotator(*rotation) if rotation else cur_rot
    unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)
    return {"location": _serialize(loc), "rotation": _serialize(rot)}


# ─── HTTP server ──────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):

    def do_GET(self) -> None:
        body = json.dumps({
            "status":   "ok",
            "app":      "UEFN Toolbelt MCP Bridge",
            "port":     _bound_port,
            "commands": sorted(_HANDLERS.keys()),
        }).encode()
        self._respond(200, body)

    def do_POST(self) -> None:
        global _request_counter
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as e:
            self._respond(400, json.dumps({"success": False, "error": f"Bad JSON: {e}"}).encode())
            return

        command = body.get("command", "")
        params  = body.get("params", {})
        if not command:
            self._respond(400, json.dumps({"success": False, "error": "Missing 'command'"}).encode())
            return

        # Direct mode: Slate ticks weren't detected at startup — run on HTTP thread.
        # Most unreal.* calls succeed from background threads inside the UEFN process.
        if _dispatch_mode == "direct":
            result = _execute_command(command, params)
            self._respond(200, json.dumps(result).encode())
            return

        _request_counter += 1
        req_id = f"req_{_request_counter}_{time.time_ns()}"
        _command_queue.put((req_id, command, params))

        deadline = time.time() + HTTP_TIMEOUT_SEC
        while time.time() < deadline:
            with _responses_lock:
                if req_id in _responses:
                    result = _responses.pop(req_id)
                    break
            time.sleep(POLL_INTERVAL_SEC)
        else:
            self._respond(504, json.dumps({"success": False, "error": f"Timeout: {command}"}).encode())
            return

        self._respond(200, json.dumps(result).encode())

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _respond(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt: str, *args: Any) -> None:
        pass  # suppress default stderr logging


# ─── Tick callback (main thread) ──────────────────────────────────────────────

def _execute_command(command: str, params: dict) -> dict:
    """Execute a command and return the response dict. Used by both tick and direct modes."""
    t0 = time.time()
    try:
        result   = _dispatch(command, params)
        response = {"success": True, "result": result}
    except Exception as e:
        _log(f"Command '{command}' failed: {e}", "error")
        response = {
            "success":   False,
            "error":     str(e),
            "traceback": traceback.format_exc(),
        }
    elapsed_ms = round((time.time() - t0) * 1000, 1)
    _history.append({"command": command, "elapsed_ms": elapsed_ms,
                     "success": response["success"]})
    return response


def _tick(delta_time: float) -> None:
    """Drain the command queue on the main thread — unreal.* calls are safe here."""
    global _tick_health
    _tick_health += 1
    processed = 0
    while not _command_queue.empty() and processed < TICK_BATCH_LIMIT:
        try:
            req_id, command, params = _command_queue.get_nowait()
        except queue.Empty:
            break

        response = _execute_command(command, params)

        with _responses_lock:
            _responses[req_id] = response
        processed += 1

    # Prune stale responses
    now = time.time()
    with _responses_lock:
        stale = [k for k in _responses
                 if float(k.split("_")[2]) / 1e9 < now - STALE_CLEANUP_SEC]
        for k in stale:
            del _responses[k]


# ─── Listener lifecycle ───────────────────────────────────────────────────────

def _find_free_port() -> int:
    for port in range(DEFAULT_PORT, MAX_PORT + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No free port in {DEFAULT_PORT}-{MAX_PORT}")


def start_listener(port: int = 0) -> int:
    """Start the MCP HTTP listener. Returns the bound port."""
    global _server, _server_thread, _tick_handle, _bound_port, _dispatch_mode, _tick_health

    if _server is not None:
        _log(f"Already running on port {_bound_port}", "warning")
        return _bound_port

    if port == 0:
        port = _find_free_port()

    _dispatch_mode = "tick"   # reset so auto-detect runs fresh on each start
    _tick_health   = 0

    _server      = HTTPServer(("127.0.0.1", port), _Handler)
    _bound_port  = port
    _start_time  = time.time()
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()

    try:
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)
        _log("Dispatch: tick-based")
    except Exception as e:
        # register_slate_post_tick_callback unavailable (e.g. headless/CI) — fall back.
        # NOTE: the old sleep-based health check was self-defeating: sleeping on the main
        # thread blocks Slate from ticking, so _tick_health never incremented and the
        # bridge always fell back to direct mode even when tick mode would work.
        _log(f"Tick callback registration failed: {e} — using direct mode", "warning")
        _dispatch_mode = "direct"

    _log(f"Listener started on http://127.0.0.1:{port}")
    _log(f"{len(_HANDLERS)} commands registered")
    return port


def stop_listener() -> None:
    """Stop the MCP HTTP listener."""
    global _server, _server_thread, _tick_handle, _bound_port

    if _server is None:
        _log("Listener is not running", "warning")
        return

    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None

    _server.shutdown()
    if _server_thread:
        _server_thread.join(timeout=3.0)

    old_port    = _bound_port
    _server     = None
    _server_thread = None
    _bound_port = 0
    _log(f"Listener stopped (was on port {old_port})")


def restart_listener(port: int = 0) -> int:
    """Restart the MCP HTTP listener."""
    stop_listener()
    time.sleep(0.5)
    return start_listener(port)


def get_status() -> dict:
    """Return current listener state."""
    return {
        "running": _server is not None,
        "port":    _bound_port,
        "url":     f"http://127.0.0.1:{_bound_port}" if _bound_port else None,
        "commands": len(_HANDLERS),
    }


# ─── Registered toolbelt tools ────────────────────────────────────────────────

@register_tool(
    name="mcp_start",
    category="MCP Bridge",
    description="Start the HTTP listener so Claude Code can control UEFN directly",
    icon="🔌",
    tags=["mcp", "listener", "bridge", "claude", "start"],
)
def mcp_start(port: int = 0, **kwargs) -> None:
    """
    Start the UEFN Toolbelt MCP HTTP listener.

    Once running, the external mcp_server.py (configured in .mcp.json) can
    control UEFN from Claude Code — spawning actors, running toolbelt tools,
    executing arbitrary Python, and more.

    Args:
        port: Port to bind to. 0 = auto-detect (tries 8765-8770).
    """
    p = start_listener(port)
    unreal.log(
        f"[MCP] ✓ Listener running on http://127.0.0.1:{p}\n"
        f"  {len(_HANDLERS)} commands available.\n"
        f"  Configure mcp_server.py in .mcp.json, then restart Claude Code."
    )


@register_tool(
    name="mcp_stop",
    category="MCP Bridge",
    description="Stop the MCP HTTP listener",
    icon="🔌",
    tags=["mcp", "listener", "bridge", "stop"],
)
def mcp_stop(**kwargs) -> None:
    """Stop the MCP HTTP listener. Claude Code will no longer be able to control UEFN."""
    stop_listener()
    unreal.log("[MCP] Listener stopped.")


@register_tool(
    name="mcp_restart",
    category="MCP Bridge",
    description="Restart the MCP HTTP listener (useful after hot-reload)",
    icon="🔄",
    tags=["mcp", "listener", "restart", "reload"],
)
def mcp_restart(port: int = 0, **kwargs) -> None:
    """Restart the listener — use this after hot-reloading the toolbelt."""
    p = restart_listener(port)
    unreal.log(f"[MCP] ✓ Restarted on http://127.0.0.1:{p}")


@register_tool(
    name="mcp_status",
    category="MCP Bridge",
    description="Print MCP listener status — port, running state, command count",
    icon="📡",
    tags=["mcp", "listener", "status"],
)
def mcp_status(**kwargs) -> None:
    """Print the current MCP listener status to the Output Log."""
    s = get_status()
    if s["running"]:
        unreal.log(
            f"\n[MCP] ═══ Listener Status ═══\n"
            f"  Running:   YES\n"
            f"  URL:       {s['url']}\n"
            f"  Commands:  {s['commands']}\n"
            f"\n  Claude Code .mcp.json config:\n"
            f'  {{"mcpServers": {{"uefn-toolbelt": {{'
            f'"command": "python", "args": ["<path>/mcp_server.py"]}}}}}}\n'
        )
    else:
        unreal.log(
            "[MCP] Listener is NOT running.\n"
            "  Start with: tb.run('mcp_start')\n"
            "  Or: Toolbelt menu → MCP Bridge → Start Listener"
        )

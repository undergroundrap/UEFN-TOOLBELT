"""
UEFN Toolbelt — External Python Client
=========================================
Stdlib-only HTTP client for the UEFN Toolbelt MCP bridge.
No MCP, no SDK, no dependencies — works from any Python 3.8+ script,
CI pipeline, Go/Rust tool (via curl), or browser (CORS enabled).

Usage:
    from client import ToolbeltClient, ToolbeltError

    ue = ToolbeltClient()                  # default: 127.0.0.1:8765
    ue.ping()
    ue.run_tool("material_apply_preset", preset="chrome")
    actors = ue.get_all_actors()
    ue.execute_python("result = unreal.EditorLevelLibrary.get_editor_world().get_name()")

Requirements:
    - UEFN is running with the Toolbelt loaded
    - MCP listener is started: tb.run("mcp_start")

Author: Ocean Bennett · License: AGPL-3.0
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


# ─── Exceptions ───────────────────────────────────────────────────────────────

class ToolbeltError(Exception):
    """A toolbelt command failed on the UEFN side."""
    def __init__(self, message: str, traceback_text: str = ""):
        super().__init__(message)
        self.traceback_text = traceback_text

    def __str__(self) -> str:
        if self.traceback_text:
            return f"{super().__str__()}\n{self.traceback_text}"
        return super().__str__()


class NotConnected(ToolbeltError):
    """The UEFN listener is not running."""
    pass


class CommandTimeout(ToolbeltError):
    """The command timed out waiting for UEFN to respond."""
    pass


# ─── Client ───────────────────────────────────────────────────────────────────

class ToolbeltClient:
    """
    HTTP client for the UEFN Toolbelt MCP bridge.

    Start the listener in UEFN first:
        import UEFN_Toolbelt as tb; tb.run("mcp_start")

    Then connect from any external script:
        ue = ToolbeltClient()
        ue.run_tool("arena_generate", size="large", apply_team_colors=True)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout: float = 30.0,
    ):
        self.url = f"http://{host}:{port}"
        self.timeout = timeout

    # ── Core transport ────────────────────────────────────────────────────────

    def _send(self, command: str, params: dict | None = None,
              timeout: float | None = None) -> Any:
        """
        Send one command to UEFN and return the result.
        Raises ToolbeltError / NotConnected / CommandTimeout on failure.
        """
        payload = json.dumps({"command": command, "params": params or {}}).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t = timeout if timeout is not None else self.timeout
        try:
            with urllib.request.urlopen(req, timeout=t) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            if "refused" in str(e).lower() or "no connection" in str(e).lower():
                raise NotConnected(
                    "UEFN Toolbelt listener is not running.\n"
                    "  Start it: import UEFN_Toolbelt as tb; tb.run('mcp_start')"
                ) from e
            raise ToolbeltError(f"HTTP error: {e}") from e
        except Exception as e:
            if "timed out" in str(e).lower():
                raise CommandTimeout(
                    f"Command '{command}' timed out after {t}s.\n"
                    "  UEFN may be processing a heavy operation."
                ) from e
            raise

        if not body.get("success", False):
            raise ToolbeltError(
                body.get("error", "Unknown error"),
                body.get("traceback", ""),
            )
        return body.get("result")

    def batch(self, commands: list[dict], timeout: float = 60.0) -> list[dict]:
        """
        Execute multiple commands in a single UEFN editor tick.
        Each entry: {"command": "name", "params": {...}}

        Faster than sending commands one-by-one for multi-step sequences.

        Example:
            ue.batch([
                {"command": "run_tool",
                 "params": {"tool_name": "snapshot_save"}},
                {"command": "run_tool",
                 "params": {"tool_name": "scatter_hism",
                            "kwargs": {"count": 200, "radius": 3000}}},
                {"command": "save_current_level", "params": {}},
            ])
        """
        result = self._send("batch_exec", {"commands": commands}, timeout=timeout)
        return result.get("results", [])

    # ── System ────────────────────────────────────────────────────────────────

    def ping(self) -> dict:
        """Check if the listener is alive. Returns port, commands, python version."""
        return self._send("ping")

    def get_log(self, last_n: int = 50) -> list[str]:
        """Get last N lines from the MCP listener log ring."""
        return self._send("get_log", {"last_n": last_n}).get("lines", [])

    def history(self, tail: int = 30) -> list[dict]:
        """Get recent command history with per-command timing."""
        return self._send("history", {"tail": tail}).get("entries", [])

    def undo(self) -> dict:
        """Undo the last editor action."""
        return self._send("undo")

    def redo(self) -> dict:
        """Redo the last undone action."""
        return self._send("redo")

    # ── Toolbelt bridge ───────────────────────────────────────────────────────

    def run_tool(self, tool_name: str, timeout: float = 120.0, **kwargs) -> dict:
        """
        Run any registered UEFN Toolbelt tool by name.
        This is the main interface — 95+ tools available.

        Examples:
            ue.run_tool("material_apply_preset", preset="chrome")
            ue.run_tool("arena_generate", size="large", apply_team_colors=True)
            ue.run_tool("scatter_hism", count=300, radius=5000.0)
            ue.run_tool("snapshot_save", name="before_cleanup")
            ue.run_tool("tag_add", key="biome", value="desert")
            ue.run_tool("screenshot_focus_selection", width=1920, height=1080)
            ue.run_tool("ref_full_report", scan_path="/Game")
        """
        return self._send(
            "run_tool",
            {"tool_name": tool_name, "kwargs": kwargs},
            timeout=timeout,
        )

    def list_tools(self, category: str = "") -> list[dict]:
        """List all registered toolbelt tools, optionally filtered by category."""
        return self._send("list_tools", {"category": category}).get("tools", [])

    def execute_python(self, code: str, timeout: float = 60.0) -> dict:
        """
        Execute arbitrary Python inside UEFN on the main thread.
        Pre-populated globals: unreal, actor_sub, asset_sub, level_sub, tb.
        Assign to `result` to return a value. Use print() for stdout.

        Example:
            r = ue.execute_python("result = actor_sub.get_all_level_actors()")
        """
        return self._send("execute_python", {"code": code}, timeout=timeout)

    # ── Actors ────────────────────────────────────────────────────────────────

    def get_all_actors(self, class_filter: str = "") -> list[dict]:
        """List all actors in the current level."""
        return self._send("get_all_actors",
                          {"class_filter": class_filter}).get("actors", [])

    def get_selected_actors(self) -> list[dict]:
        """Get actors currently selected in the UEFN viewport."""
        return self._send("get_selected_actors").get("actors", [])

    def spawn_actor(
        self,
        asset_path: str = "",
        actor_class: str = "",
        location: Optional[list[float]] = None,
        rotation: Optional[list[float]] = None,
        label: str = "",
    ) -> dict:
        """Spawn an actor. Provide asset_path OR actor_class."""
        params: dict[str, Any] = {}
        if asset_path:  params["asset_path"]  = asset_path
        if actor_class: params["actor_class"] = actor_class
        if location:    params["location"]    = location
        if rotation:    params["rotation"]    = rotation
        if label:       params["label"]       = label
        return self._send("spawn_actor", params).get("actor", {})

    def set_actor_property(self, actor_path: str, property_name: str, value) -> dict:
        """Set a single editor property on an actor by path or label."""
        return self._send("set_actor_property", {
            "actor_path": actor_path, "property_name": property_name, "value": value,
        })

    def delete_actors(self, actor_paths: list[str]) -> dict:
        """Delete actors by path name or label."""
        return self._send("delete_actors", {"actor_paths": actor_paths})

    def set_actor_transform(
        self,
        actor_path: str,
        location: Optional[list[float]] = None,
        rotation: Optional[list[float]] = None,
        scale:    Optional[list[float]] = None,
    ) -> dict:
        """Set location, rotation and/or scale on an actor."""
        params: dict[str, Any] = {"actor_path": actor_path}
        if location: params["location"] = location
        if rotation: params["rotation"] = rotation
        if scale:    params["scale"]    = scale
        return self._send("set_actor_transform", params).get("actor", {})

    # ── Assets ────────────────────────────────────────────────────────────────

    def list_assets(self, directory: str = "/Game/",
                    recursive: bool = True, class_filter: str = "") -> list[str]:
        """List asset paths in a Content Browser directory."""
        return self._send("list_assets", {
            "directory": directory,
            "recursive": recursive,
            "class_filter": class_filter,
        }).get("assets", [])

    def get_asset_info(self, asset_path: str) -> dict:
        """Get metadata for an asset."""
        return self._send("get_asset_info", {"asset_path": asset_path}).get("asset", {})

    def import_asset(
        self,
        source_file: str,
        destination_path: str,
        replace_existing: bool = True,
        save: bool = True,
    ) -> dict:
        """Import an external file into the Content Browser."""
        return self._send("import_asset", {
            "source_file":      source_file,
            "destination_path": destination_path,
            "replace_existing": replace_existing,
            "save":             save,
        })

    def save_asset(self, asset_path: str) -> bool:
        """Save a modified asset."""
        return self._send("save_asset", {"asset_path": asset_path}).get("success", False)

    def rename_asset(self, old_path: str, new_path: str) -> bool:
        """Rename or move an asset."""
        return self._send("rename_asset", {
            "old_path": old_path, "new_path": new_path
        }).get("success", False)

    def duplicate_asset(self, source_path: str, dest_path: str) -> bool:
        """Duplicate an asset."""
        return self._send("duplicate_asset", {
            "source_path": source_path, "dest_path": dest_path
        }).get("success", False)

    def delete_asset(self, asset_path: str) -> bool:
        """Delete an asset."""
        return self._send("delete_asset", {"asset_path": asset_path}).get("success", False)

    def create_material_instance(
        self,
        parent_path: str,
        instance_name: str,
        destination: str = "/Game/Materials",
        scalar_params: Optional[dict[str, float]] = None,
        vector_params: Optional[dict[str, list[float]]] = None,
        texture_params: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Create a new MaterialInstanceConstant from a parent material.
        Returns the path of the created MI.

        Example:
            path = ue.create_material_instance(
                parent_path="/Game/Materials/M_Master",
                instance_name="MI_Red",
                destination="/Game/Materials/Instances",
                scalar_params={"Roughness": 0.2, "Metallic": 0.8},
                vector_params={"BaseColor": [1.0, 0.1, 0.1, 1.0]},
            )
        """
        return self._send("create_material_instance", {
            "parent_path":    parent_path,
            "instance_name":  instance_name,
            "destination":    destination,
            "scalar_params":  scalar_params or {},
            "vector_params":  vector_params or {},
            "texture_params": texture_params or {},
        }).get("path", "")

    # ── Level & viewport ──────────────────────────────────────────────────────

    def save_level(self) -> bool:
        """Save the current level."""
        return self._send("save_current_level").get("success", False)

    def get_level_info(self) -> dict:
        """Get world name and actor count."""
        return self._send("get_level_info")

    def get_camera(self) -> dict:
        """Get viewport camera location and rotation."""
        return self._send("get_viewport_camera")

    def set_camera(
        self,
        location: Optional[list[float]] = None,
        rotation: Optional[list[float]] = None,
    ) -> dict:
        """Move the viewport camera."""
        params: dict[str, Any] = {}
        if location: params["location"] = location
        if rotation: params["rotation"] = rotation
        return self._send("set_viewport_camera", params)


# ─── Quick connect helper ─────────────────────────────────────────────────────

def connect(port: int = 8765, timeout: float = 30.0) -> ToolbeltClient:
    """Create a client and verify the connection with a ping."""
    client = ToolbeltClient(port=port, timeout=timeout)
    client.ping()   # raises NotConnected if listener isn't running
    return client

"""
UEFN Toolbelt — External Python Client
=========================================
Stdlib-only HTTP client for the UEFN Toolbelt MCP bridge.
No MCP, no SDK, no dependencies — works from any Python 3.8+ script,
or trusted same-user local automation.

Usage:
    from client import ToolbeltClient, ToolbeltError

    ue = ToolbeltClient()                  # loads the current local session handoff
    ue.ping()
    ue.run_tool("material_apply_preset", preset="chrome")
    actors = ue.get_all_actors()

Requirements:
    - UEFN is running with the Toolbelt loaded
    - MCP listener is started: tb.run("mcp_start")

Author: Ocean Bennett · License: AGPL-3.0
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _redact_secret(value: Any, secret: str) -> Any:
    """Defensively remove the current handoff credential from client output."""
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        return {
            _redact_secret(key, secret): _redact_secret(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_secret(item, secret) for item in value)
    return value

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


class CommandTimeout(ToolbeltError):
    """The command timed out waiting for UEFN to respond."""


class AuthenticationError(ToolbeltError):
    """The local session credential is missing, stale, or rejected."""


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
        port: int | None = None,
        timeout: float = 30.0,
        token_file: str | os.PathLike[str] | None = None,
    ):
        if host != "127.0.0.1":
            raise ValueError("The Toolbelt client only accepts the loopback host")
        self._port_override = port
        self.timeout = timeout
        self._token_file = Path(token_file) if token_file else self._default_token_file()

    @staticmethod
    def _default_token_file() -> Path:
        override = os.environ.get("UEFN_MCP_TOKEN_FILE", "").strip()
        if override:
            return Path(override).expanduser()
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if not local_app_data:
            raise AuthenticationError(
                "LOCALAPPDATA is unset; the UEFN MCP session handoff cannot be located"
            )
        return (
            Path(local_app_data)
            / "UnrealEditorFortnite"
            / "Saved"
            / "UEFN_Toolbelt"
            / "mcp_session.json"
        )

    def _session(self) -> tuple[str, str]:
        try:
            payload = json.loads(self._token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthenticationError(
                "UEFN MCP session is unavailable; start or restart the listener"
            ) from exc
        if not isinstance(payload, dict):
            raise AuthenticationError("UEFN MCP session handoff is invalid")
        host = payload.get("host")
        port = self._port_override if self._port_override is not None else payload.get("port")
        token = payload.get("token")
        if (
            payload.get("version") != 1
            or host != "127.0.0.1"
            or not isinstance(port, int)
            or not (1 <= port <= 65535)
            or not isinstance(token, str)
            or len(token) < 32
        ):
            raise AuthenticationError("UEFN MCP session handoff is invalid")
        return f"http://127.0.0.1:{port}", token

    # ── Core transport ────────────────────────────────────────────────────────

    def _send(self, command: str, params: dict | None = None,
              timeout: float | None = None) -> Any:
        """
        Send one command to UEFN and return the result.
        Raises ToolbeltError / NotConnected / CommandTimeout on failure.
        """
        url, token = self._session()
        payload = json.dumps({"command": command, "params": params or {}}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t = timeout if timeout is not None else self.timeout
        try:
            with urllib.request.urlopen(req, timeout=t) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AuthenticationError(
                    "UEFN MCP authentication failed; restart the listener"
                ) from None
            raise ToolbeltError(f"UEFN MCP request rejected with HTTP {e.code}") from None
        except urllib.error.URLError as e:
            detail = _redact_secret(str(e), token)
            if "refused" in detail.lower() or "no connection" in detail.lower():
                raise NotConnected(
                    "UEFN Toolbelt listener is not running.\n"
                    "  Start it: import UEFN_Toolbelt as tb; tb.run('mcp_start')"
                ) from None
            raise NotConnected("UEFN Toolbelt listener could not be reached") from None
        except Exception as e:
            detail = _redact_secret(str(e), token)
            if "timed out" in detail.lower():
                raise CommandTimeout(
                    f"Command '{_redact_secret(command, token)}' timed out after {t}s.\n"
                    "  UEFN may be processing a heavy operation."
                ) from None
            raise ToolbeltError(detail) from None

        body = _redact_secret(body, token)

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
        This is the main interface — 362 tools available.

        Examples:
            ue.run_tool("material_apply_preset", preset="chrome")
            ue.run_tool("arena_generate", size="large", apply_team_colors=True)
            ue.run_tool("scatter_hism", count=300, radius=5000.0)
            ue.run_tool("snapshot_save", name="before_cleanup")
            ue.run_tool("tag_add", key="biome", value="desert")
            ue.run_tool("screenshot_focus_selection", width=1920, height=1080)
            ue.run_tool("ref_full_report", scan_path="")
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
        """Reject arbitrary remote Python; use the local UEFN console instead."""
        raise ToolbeltError(
            "execute_python is unavailable on the Toolbelt MCP bridge; "
            "use the local UEFN Python console"
        )

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
        location: list[float] | None = None,
        rotation: list[float] | None = None,
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
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        scale:    list[float] | None = None,
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
        scalar_params: dict[str, float] | None = None,
        vector_params: dict[str, list[float]] | None = None,
        texture_params: dict[str, str] | None = None,
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
        location: list[float] | None = None,
        rotation: list[float] | None = None,
    ) -> dict:
        """Move the viewport camera."""
        params: dict[str, Any] = {}
        if location: params["location"] = location
        if rotation: params["rotation"] = rotation
        return self._send("set_viewport_camera", params)


# ─── Quick connect helper ─────────────────────────────────────────────────────

def connect(port: int | None = None, timeout: float = 30.0) -> ToolbeltClient:
    """Create a client and verify the connection with a ping."""
    client = ToolbeltClient(port=port, timeout=timeout)
    client.ping()   # raises NotConnected if listener isn't running
    return client

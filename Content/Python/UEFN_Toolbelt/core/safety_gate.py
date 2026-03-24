import os
import unreal
from ..registry import register_tool
from ..core import log_info, log_warning, log_error, PLUGIN_MOUNTS

# Engine / plugin mounts that must never be written to.
# Sourced from core.PLUGIN_MOUNTS — single source of truth (see UEFN_QUIRKS.md Quirk #23).
_BLOCKED_MOUNTS = PLUGIN_MOUNTS | frozenset({"Fortnite", "Epic"})


class SafetyGate:
    """
    Central safety layer for all UEFN Toolbelt 'Write' operations.
    Prevents accidental modification of Epic/Fortnite system assets and
    enforces project-relative path validation.

    UEFN note: the user's project uses a named mount (e.g. /BRCosmetics/,
    /Device_API_Mapping/) — NOT /Game/. Checking only for /Game/ blocks all
    legitimate project writes. We check the mount root against _BLOCKED_MOUNTS
    instead. See docs/UEFN_QUIRKS.md Quirk #23.
    """

    @staticmethod
    def is_safe_to_modify(asset_path: str):
        """
        Checks if an asset path is safe to modify.
        Returns (bool, reason).
        """
        normalized = asset_path.replace("\\", "/")

        # Always allow VerseLocal
        if normalized.startswith("/VerseLocal/"):
            return True, "Asset is in a modifiable project directory."

        # Extract the top-level mount root
        root = normalized.strip("/").split("/")[0] if normalized.strip("/") else ""

        if not root:
            return False, f"BLOCKED: Empty or invalid asset path '{asset_path}'."

        if root in _BLOCKED_MOUNTS:
            return False, (
                f"BLOCKED: Asset '{asset_path}' is in a system/engine mount "
                f"(/{root}/) and must not be modified."
            )

        return True, "Asset is in a modifiable project directory."

    @staticmethod
    def enforce_safety(asset_path: str):
        """Raises PermissionError if the asset is not safe to modify."""
        is_safe, reason = SafetyGate.is_safe_to_modify(asset_path)
        if not is_safe:
            log_error(reason)
            raise PermissionError(reason)
        return True

    @staticmethod
    def get_project_content_dir():
        """Returns the absolute path to the project's Content directory on disk."""
        # project_content_dir() returns the FortniteGame engine path in UEFN.
        # Use project_dir() + /Content instead. See UEFN_QUIRKS.md Quirk #23.
        root = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_dir()
        ).rstrip("/\\")
        return root + "/Content"

@register_tool(name="core_safety_audit", category="System")
def core_safety_audit():
    """
    Checks the current UEFN viewport selection against Safety Gate rules.
    Identifies which assets are safe for AI/Automation to modify.
    """
    actors = unreal.EditorLevelLibrary.get_selected_level_actors() or []
    if not actors:
        log_warning("Safety Audit: No actors selected.")
        return "No actors selected."
        
    results = []
    for actor in actors:
        path = actor.get_path_name()
        is_safe, reason = SafetyGate.is_safe_to_modify(path)
        status = "✅ SAFE" if is_safe else "❌ BLOCKED"
        results.append(f"{status} | {actor.get_name()} ({reason})")
        
    log_info(f"Safety Audit complete for {len(actors)} actors.")
    return "\n".join(results)

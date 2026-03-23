import os
import unreal
from ..registry import register_tool
from ..core import log_info, log_warning, log_error

class SafetyGate:
    """
    Central safety layer for all UEFN Toolbelt 'Write' operations.
    Prevents accidental modification of Epic/Fortnite system assets and
    enforces project-relative path validation.
    """
    
    @staticmethod
    def is_safe_to_modify(asset_path):
        """
        Checks if an asset path is safe to modify.
        Returns (bool, reason)
        """
        # 1. Check if path starts with /Game/ (User project)
        # Avoid /Epic/, /Fortnite/, /Engine/, /Paper2D/, etc.
        safe_prefixes = ["/Game/", "/VerseLocal/"]
        
        normalized_path = asset_path.replace("\\", "/")
        if not any(normalized_path.startswith(prefix) for prefix in safe_prefixes):
            return False, f"BLOCKED: Asset '{asset_path}' is a system/engine asset and must not be modified."
        
        # 2. Check for 'Cooked' status if possible (EditorAssetSubsystem usually handles this)
        # But we can add a manual check if needed via asset registry flags
        
        return True, "Asset is in a modifiable project directory."

    @staticmethod
    def enforce_safety(asset_path):
        """
        Raises an exception if the asset is not safe to modify.
        """
        is_safe, reason = SafetyGate.is_safe_to_modify(asset_path)
        if not is_safe:
            log_error(reason)
            raise PermissionError(reason)
        return True

    @staticmethod
    def get_project_content_dir():
        """Returns the absolute path to the project's Content directory."""
        return unreal.Paths.project_content_dir()

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

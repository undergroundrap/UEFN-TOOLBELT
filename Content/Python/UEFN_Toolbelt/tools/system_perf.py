"""
UEFN TOOLBELT — System Performance Optimizer
========================================
Native system tools for managing UEFN engine performance states.
Specifically built to prevent "Background Throttling", which causes UEFN to drop
to 3 FPS when you alt-tab to a web browser or AI Coding Assistant window.

FEATURES:
  • Toggles `EditorPerformanceSettings.bEnableEditorPerformanceSaving`
  • Overrides console FPS limits to maintain live Python execution speeds
  • Completely native code, zero external dependencies.
"""

from __future__ import annotations

import unreal
from ..core import log_info, log_error
from ..registry import register_tool

@register_tool(
    name="system_optimize_background_cpu",
    category="System",
    description="Disables UEFN sleep state when alt-tabbed, ensuring Python executing from AI runs at max speed.",
    tags=["system", "fps", "throttle", "background", "ai", "performance", "optimize"]
)
def run_optimize_background_cpu(
    max_performance: bool = True,
    **kwargs
) -> dict:
    """
    Toggles 'Use Less CPU when in Background'.
    When doing heavy Python/MCP scripting via LLM, UEFN must not sleep.
    
    Args:
        max_performance: If True, disables power saving so UEFN runs at full speed in the background.
                         If False, restores UEFN to default power saving mode.
    """
    try:
        # 1. Update the Editor Performance Settings Object
        settings = unreal.get_default_object(unreal.EditorPerformanceSettings)
        
        # When max_performance is True, we DISABLE performance saving
        settings.b_enable_editor_performance_saving = not max_performance
        
        # 2. Issue Raw Engine Console Commands for brute-force override
        if max_performance:
            # Force background IDLE loop to stay fully active
            unreal.SystemLibrary.execute_console_command(None, "t.IdleWhenNotForeground 0")
            unreal.SystemLibrary.execute_console_command(None, "t.MaxFPS 60")
            status_msg = "Max Performance Active (Background CPU throttling disabled)"
        else:
            # Restore to standard power saving limits
            unreal.SystemLibrary.execute_console_command(None, "t.IdleWhenNotForeground 1")
            unreal.SystemLibrary.execute_console_command(None, "t.MaxFPS 120")
            status_msg = "Standard Power Saving Active (Background CPU throttling enabled)"
            
        log_info(f"System Optimization: {status_msg}")
        
        return {
            "max_performance": max_performance,
            "throttle_active": not max_performance,
            "status": status_msg
        }
        
    except Exception as e:
        log_error(f"Failed to update system performance settings: {e}")
        return {"error": str(e)}


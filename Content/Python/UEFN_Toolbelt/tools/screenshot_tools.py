"""
UEFN TOOLBELT — screenshot_tools.py
=========================================
Capture high-resolution screenshots from the UEFN editor viewport.

Why this matters:
  UEFN creators constantly need marketing renders, layout previews, and
  comparison shots. Doing it through the editor menus is tedious; doing
  it from Python means you can automate it, batch it, and name the files
  meaningfully — all from a single button click.

API used:
  unreal.AutomationLibrary.take_high_res_screenshot(
      res_x, res_y, filename, camera=None,
      capture_hdr=False, force_game_view=False
  )
  Confirmed 10/10 available in UEFN 40.00+ (Kirch API dump, March 2026).

  unreal.EditorLevelLibrary.get_level_viewport_camera_info()
  unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)

Output folder:
  Saved/UEFN_Toolbelt/screenshots/  (created on first use)

Filename convention:
  {name}_{YYYYMMDD_HHMMSS}_{WxH}.png

Tools:
  screenshot_take            — capture viewport at any resolution
  screenshot_focus_selection — zoom to selection, capture, restore camera
  screenshot_timed_series    — take N screenshots with a delay between each
                               (useful for before/after comparisons)
  screenshot_open_folder     — print the output folder path (for quick access)

Notes:
  - All screenshots land in Saved/UEFN_Toolbelt/screenshots/
  - HDR capture stores 16-bit EXR alongside the PNG when capture_hdr=True
  - Camera restore after screenshot_focus_selection is always attempted,
    even if the screenshot itself fails (finally block)
  - UEFN Python runs on the main thread — take_high_res_screenshot is
    synchronous but may stall the editor for a frame on large scenes
"""

from __future__ import annotations

import math
import os
import time
from typing import Optional

import unreal

from UEFN_Toolbelt.core import actors_bounding_box, get_selected_actors
from UEFN_Toolbelt.registry import register_tool

# ─── Output paths ─────────────────────────────────────────────────────────────

_SAVED       = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
_SHOT_DIR    = os.path.join(_SAVED, "screenshots")


def _ensure_dir() -> None:
    os.makedirs(_SHOT_DIR, exist_ok=True)


def _timestamped(name: str, width: int, height: int) -> str:
    """Build an absolute file path with a timestamp in the filename."""
    ts  = time.strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    return os.path.join(_SHOT_DIR, f"{safe_name}_{ts}_{width}x{height}.png")


# ─── Camera helpers ───────────────────────────────────────────────────────────

def _get_camera() -> tuple[unreal.Vector, unreal.Rotator]:
    """Return current viewport camera (location, rotation)."""
    return unreal.EditorLevelLibrary.get_level_viewport_camera_info()


def _set_camera(loc: unreal.Vector, rot: unreal.Rotator) -> None:
    """Set viewport camera position."""
    unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)


def _camera_for_bounds(
    center: unreal.Vector,
    half_size: unreal.Vector,
    fov_deg: float = 60.0,
    padding: float = 1.3,
) -> tuple[unreal.Vector, unreal.Rotator]:
    """
    Compute a camera position that frames an AABB (Axis-Aligned Bounding Box).

    Strategy:
      - Look straight down from above at a slight angle so the layout is clear.
      - Place the camera far enough back that the entire bounding box fits.
      - Aim at the bounding box center.

    Args:
        center:   World-space center of the AABB.
        half_size: Half-extents of the AABB (X, Y, Z).
        fov_deg:  Camera field-of-view in degrees.
        padding:  Multiplier for extra margin (1.3 = 30% breathing room).
    """
    # Bounding sphere radius
    radius = math.sqrt(half_size.x ** 2 + half_size.y ** 2 + half_size.z ** 2)

    # Distance needed so the sphere fills the FOV
    half_fov_rad = math.radians(fov_deg / 2.0)
    dist = (radius * padding) / math.tan(half_fov_rad)

    # Camera positioned above-and-back; looking down at 40° pitch
    pitch = -40.0
    yaw   = 45.0   # diagonal view is more interesting than pure overhead

    pitch_rad = math.radians(pitch)
    yaw_rad   = math.radians(yaw)

    offset = unreal.Vector(
        dist * math.cos(pitch_rad) * math.cos(yaw_rad),
        dist * math.cos(pitch_rad) * math.sin(yaw_rad),
        -dist * math.sin(pitch_rad),   # negative pitch → positive Z offset
    )

    cam_loc = unreal.Vector(
        center.x + offset.x,
        center.y + offset.y,
        center.z + offset.z,
    )
    cam_rot = unreal.Rotator(pitch, yaw + 180.0, 0.0)  # +180 to look back at center

    return cam_loc, cam_rot


# ─── Core screenshot helper ───────────────────────────────────────────────────

def _take_shot(
    out_path: str,
    width: int,
    height: int,
    camera: Optional[unreal.CameraActor] = None,
    capture_hdr: bool = False,
    force_game_view: bool = False,
) -> bool:
    """
    Call AutomationLibrary.take_high_res_screenshot and return success.

    UEFN 40.00+ confirmed — Kirch capabilities doc, Screenshots & Testing 10/10.
    """
    try:
        unreal.AutomationLibrary.take_high_res_screenshot(
            res_x=width,
            res_y=height,
            filename=out_path,
            camera=camera,
            capture_hdr=capture_hdr,
            force_game_view=force_game_view,
        )
        return True
    except Exception as e:
        unreal.log_error(f"[Screenshot] take_high_res_screenshot failed: {e}")
        return False


# ─── Tool implementations ─────────────────────────────────────────────────────

def _do_take(name: str, width: int, height: int,
             capture_hdr: bool, force_game_view: bool) -> str:
    _ensure_dir()
    out = _timestamped(name, width, height)
    unreal.log(f"[Screenshot] Capturing {width}×{height}…")

    ok = _take_shot(out, width, height, None, capture_hdr, force_game_view)

    if ok:
        unreal.log(f"[Screenshot] ✓  {out}")
        return out
    else:
        unreal.log_warning(f"[Screenshot] ✗  Capture may have failed — check {_SHOT_DIR}")
        return ""


def _do_focus_selection(
    name: str,
    width: int,
    height: int,
    fov_deg: float,
    restore_camera: bool,
) -> str:
    actors = get_selected_actors()
    if not actors:
        unreal.log_warning("[Screenshot] Nothing selected. Select actors first.")
        return ""

    try:
        center, extent = actors_bounding_box(actors)
    except ValueError as e:
        unreal.log_warning(f"[Screenshot] {e}")
        return ""

    # Half-extents as Vector
    half = unreal.Vector(extent.x / 2.0, extent.y / 2.0, extent.z / 2.0)
    cam_loc, cam_rot = _camera_for_bounds(center, half, fov_deg)

    saved_loc, saved_rot = _get_camera()

    _ensure_dir()
    out = _timestamped(name, width, height)
    result = ""

    try:
        _set_camera(cam_loc, cam_rot)
        # Give Slate one frame to update the viewport before capturing
        unreal.log(f"[Screenshot] Framing selection and capturing {width}×{height}…")
        ok = _take_shot(out, width, height)
        if ok:
            unreal.log(f"[Screenshot] ✓  {out}")
            result = out
        else:
            unreal.log_warning(f"[Screenshot] ✗  Capture may have failed — check {_SHOT_DIR}")
    finally:
        if restore_camera:
            _set_camera(saved_loc, saved_rot)
            unreal.log("[Screenshot]   Camera restored.")

    return result


def _do_timed_series(
    name: str,
    count: int,
    width: int,
    height: int,
    interval_sec: float,
) -> None:
    _ensure_dir()
    unreal.log(
        f"[Screenshot] Starting series of {count} screenshots "
        f"every {interval_sec:.1f}s…"
    )

    ok_count = 0
    start_t  = time.time()

    for i in range(count):
        series_name = f"{name}_f{i + 1:03d}"
        out = _timestamped(series_name, width, height)

        if _take_shot(out, width, height):
            ok_count += 1
            unreal.log(f"[Screenshot]   {i + 1}/{count}  ✓  {os.path.basename(out)}")
        else:
            unreal.log_warning(f"[Screenshot]   {i + 1}/{count}  ✗  failed")

        if i < count - 1:
            time.sleep(interval_sec)

    elapsed = time.time() - start_t
    unreal.log(
        f"[Screenshot] ✓ Series done — {ok_count}/{count} captured in {elapsed:.1f}s"
        f"\n  Output: {_SHOT_DIR}"
    )


# ─── Registered tools ─────────────────────────────────────────────────────────

@register_tool(
    name="screenshot_take",
    category="Screenshot",
    description="Capture the viewport at any resolution to Saved/UEFN_Toolbelt/screenshots/",
    icon="📷",
    tags=["screenshot", "capture", "render", "viewport"],
)
def screenshot_take(
    name: str = "viewport",
    width: int = 1920,
    height: int = 1080,
    capture_hdr: bool = False,
    force_game_view: bool = False,
    **kwargs,
) -> dict:
    """
    Take a high-resolution screenshot of the current editor viewport.

    Args:
        name:            Filename prefix. Timestamp and resolution are appended.
        width / height:  Output resolution in pixels. Common values:
                            1920×1080  Full HD
                            2560×1440  2K / QHD
                            3840×2160  4K / UHD
        capture_hdr:     Also write a 16-bit EXR alongside the PNG.
        force_game_view: Hide editor UI gizmos (cleaner output).

    Returns:
        dict: {"status", "path"} — path is the output file (queued, ~1s to appear).

    Output:
        Saved/UEFN_Toolbelt/screenshots/{name}_{YYYYMMDD_HHMMSS}_{W}x{H}.png
    """
    path = _do_take(name, width, height, capture_hdr, force_game_view)
    return {"status": "ok" if path else "error", "path": path}


@register_tool(
    name="screenshot_focus_selection",
    category="Screenshot",
    description="Frame the current selection, capture a screenshot, then restore the camera",
    icon="🎯",
    tags=["screenshot", "capture", "selection", "frame", "focus"],
)
def screenshot_focus_selection(
    name: str = "selection",
    width: int = 1920,
    height: int = 1080,
    fov_deg: float = 60.0,
    restore_camera: bool = True,
    **kwargs,
) -> dict:
    """
    Automatically frame all selected actors, capture a screenshot, and
    (optionally) restore the camera to its pre-shot position.

    Steps:
      1. Compute the AABB of all selected actors.
      2. Calculate an optimal camera position and angle to frame it.
      3. Move the viewport camera there.
      4. Capture.
      5. Restore camera (unless restore_camera=False).

    Args:
        name:           Filename prefix.
        width / height: Output resolution in pixels.
        fov_deg:        Field-of-view used for distance calculation.
                        Match your actual viewport FOV for best results.
        restore_camera: If True (default), camera returns to its pre-shot
                        position after the capture. Set False for manual
                        fine-tuning: position stays where the auto-framer
                        put it so you can adjust from there.

    Returns:
        dict: {"status", "path"} — path is queued output file (~1s to appear).
    """
    path = _do_focus_selection(name, width, height, fov_deg, restore_camera)
    return {"status": "ok" if path else "error", "path": path}


@register_tool(
    name="screenshot_timed_series",
    category="Screenshot",
    description="Take N screenshots at a timed interval — for before/after comparisons",
    icon="🎞",
    tags=["screenshot", "capture", "series", "timelapse", "compare"],
)
def screenshot_timed_series(
    name: str = "series",
    count: int = 3,
    width: int = 1920,
    height: int = 1080,
    interval_sec: float = 2.0,
    **kwargs,
) -> dict:
    """
    Capture a series of screenshots at regular intervals from the current camera.

    Useful for:
      - Before/during/after shots of a large operation (3 count, 0s interval)
      - Timelapse during a long scatter or generation operation
      - Comparison renders at different quality settings

    Args:
        name:         Filename prefix for all shots in the series.
        count:        Number of screenshots to take.
        width / height: Resolution in pixels.
        interval_sec: Seconds to wait between shots.
                      0 = fire all shots immediately (back-to-back).
    """
    if count < 1:
        unreal.log_warning("[Screenshot] count must be at least 1.")
        return {"status": "error", "message": "count must be at least 1"}
    _do_timed_series(name, count, width, height, max(0.0, interval_sec))
    return {"status": "ok", "count": count, "folder": _SHOT_DIR}


@register_tool(
    name="screenshot_open_folder",
    category="Screenshot",
    description="Print the screenshots output folder path to the Output Log",
    icon="📁",
    tags=["screenshot", "folder", "path", "output"],
)
def screenshot_open_folder(**kwargs) -> dict:
    """
    Print the screenshot output folder path so you can find your shots quickly.

    Returns:
        dict: {"status", "path", "file_count"}
    """
    _ensure_dir()
    try:
        files = [f for f in os.listdir(_SHOT_DIR) if f.endswith((".png", ".exr"))]
    except Exception:
        files = []

    unreal.log(f"\n[Screenshot] Output folder: {_SHOT_DIR}")
    unreal.log(f"  {len(files)} file(s) saved so far.\n")
    return {"status": "ok", "path": _SHOT_DIR, "file_count": len(files)}

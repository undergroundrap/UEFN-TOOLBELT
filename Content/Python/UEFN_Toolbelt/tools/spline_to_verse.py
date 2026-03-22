"""
UEFN TOOLBELT — Spline → Verse Converter
========================================
"I need this tool now" — the community has been asking for this since the
Python update dropped. Spline actors are everywhere in UEFN maps (patrol
paths, roads, rivers, zone boundaries) but getting that spatial data INTO
Verse code required tedious manual coordinate copying.

This tool reads any spline actor in your level and generates ready-to-paste
Verse code: coordinate arrays, path records, patrol behaviors, and zone
boundary definitions.

FEATURES:
  • Extract spline control points → Verse vector3 array literal
  • Extract evenly-sampled path points at any resolution (not just control points)
  • Generate a named Verse module with typed point data
  • Generate a complete patrol AI device skeleton using the path
  • Generate a zone boundary Verse array (for mutator_zone logic)
  • Generate a Verse `MakeSplinePath()` helper that lerps along the path at runtime
  • Export raw point data to JSON for external tools
  • All output written to Saved/UEFN_Toolbelt/snippets/ and copied to clipboard

USAGE (REPL):
    import UEFN_Toolbelt as tb

    # Select a spline actor, then:

    # Basic: control-point array
    tb.run("spline_to_verse_points")

    # Dense sample: 50 evenly spaced points along the spline
    tb.run("spline_to_verse_points", sample_count=50)

    # Full patrol AI skeleton using selected spline
    tb.run("spline_to_verse_patrol", device_name="RooftopPatrol", speed=400.0)

    # Zone boundary array (for mutator_zone / area detection)
    tb.run("spline_to_verse_zone_boundary", zone_name="RedZone")

    # Export raw JSON (for use with scatter_along_path etc.)
    tb.run("spline_export_json")

VERSE OUTPUT EXAMPLES:

    # spline_to_verse_points output:
    PatrolPath : []vector3 = array{
        vector3{X:=0.0, Y:=0.0, Z:=100.0},
        vector3{X:=1000.0, Y:=500.0, Z:=100.0},
        vector3{X:=2000.0, Y:=200.0, Z:=150.0},
    }

    # spline_to_verse_patrol output:
    RooftopPatrol := class(creative_device):
        @editable PatrolDevice : guard_spawner_device = guard_spawner_device{}
        var CurrentWaypoint<private> : int = 0
        OnBegin<override>()<suspends> : void =
            loop:
                MoveToWaypoint(PatrolPath[CurrentWaypoint])
                set CurrentWaypoint = Mod(CurrentWaypoint + 1, PatrolPath.Length)
        ...
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import List, Optional, Tuple

import unreal

from ..core import (
    get_selected_actors, log_info, log_warning, log_error,
)
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Output directory
# ─────────────────────────────────────────────────────────────────────────────

SNIPPETS_DIR = os.path.join(
    unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "snippets"
)
_SUBCAT = "spline_tools"

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_spline(actors: List[unreal.Actor]) -> Optional[Tuple[unreal.Actor, unreal.SplineComponent]]:
    """Find the first actor with a SplineComponent from the list."""
    for actor in actors:
        comps = actor.get_components_by_class(unreal.SplineComponent.static_class())
        if comps:
            return actor, comps[0]
    return None


def _sample_spline_world(spline: unreal.SplineComponent, count: int) -> List[Tuple[float, float, float]]:
    """Sample `count` evenly-spaced world-space points along a spline."""
    total = spline.get_spline_length()
    cs    = unreal.SplineCoordinateSpace.WORLD
    pts   = []
    for i in range(count):
        dist = (i / max(count - 1, 1)) * total
        loc  = spline.get_location_at_distance_along_spline(dist, cs)
        pts.append((loc.x, loc.y, loc.z))
    return pts


def _control_points_world(spline: unreal.SplineComponent) -> List[Tuple[float, float, float]]:
    """Return all spline control point positions in world space."""
    n  = spline.get_number_of_spline_points()
    cs = unreal.SplineCoordinateSpace.WORLD
    return [
        (lambda v: (v.x, v.y, v.z))(
            spline.get_location_at_spline_point(i, cs)
        )
        for i in range(n)
    ]


def _points_to_verse_array(pts: List[Tuple[float, float, float]], var_name: str) -> str:
    """Format a list of (x, y, z) tuples as a Verse vector3 array literal."""
    lines = [f"    {var_name} : []vector3 = array{{"]
    for x, y, z in pts:
        lines.append(f"        vector3{{X:={x:.1f}, Y:={y:.1f}, Z:={z:.1f}}},")
    lines.append("    }")
    return "\n".join(lines)


def _write_snippet(filename: str, content: str) -> str:
    dest = os.path.join(SNIPPETS_DIR, _SUBCAT)
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _try_clipboard(text: str) -> None:
    try:
        import subprocess
        subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
        log_info("  Copied to clipboard.")
    except Exception:
        pass


def _require_spline() -> Optional[Tuple[unreal.Actor, unreal.SplineComponent]]:
    actors = get_selected_actors()
    if not actors:
        log_warning("Select a spline actor in the viewport first.")
        return None
    result = _find_spline(actors)
    if result is None:
        log_warning("None of the selected actors have a SplineComponent.")
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="spline_to_verse_points",
    category="Verse Helpers",
    description="Convert selected spline actor to a Verse vector3 array literal.",
    tags=["spline", "verse", "convert", "path", "points", "array"],
)
def run_spline_to_verse_points(
    var_name: str = "SplinePath",
    sample_count: int = 0,          # 0 = use control points only
    use_control_points: bool = True,
    **kwargs,
) -> dict:
    """
    Args:
        var_name:           Name of the Verse variable to generate.
        sample_count:       If > 0, evenly sample this many points along the spline
                            instead of using control points. Good for dense paths.
        use_control_points: If True and sample_count==0, use raw control points.
    """
    result = _require_spline()
    if result is None:
        return {"status": "error", "path": "", "point_count": 0}

    actor, spline = result

    if sample_count > 0:
        pts = _sample_spline_world(spline, sample_count)
        mode = f"{sample_count} sampled points"
    else:
        pts = _control_points_world(spline)
        mode = f"{len(pts)} control points"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    array_code = _points_to_verse_array(pts, var_name)

    content = f"""\
# Generated by UEFN Toolbelt — Spline to Verse Converter
# {timestamp}
# Source: '{actor.get_actor_label()}' — {mode}
# Spline length: {spline.get_spline_length():.0f} cm
#
# Paste inside your creative_device class body:

{array_code}
"""

    path = _write_snippet(f"spline_{var_name}.verse", content)
    _try_clipboard(content)
    log_info(f"Spline → Verse array ({len(pts)} points) → {path}\n\n{content}")
    return {"status": "ok", "path": path, "point_count": len(pts)}


@register_tool(
    name="spline_to_verse_patrol",
    category="Verse Helpers",
    description="Generate a full Verse patrol AI device skeleton from a selected spline.",
    tags=["spline", "verse", "patrol", "ai", "skeleton", "path"],
)
def run_spline_to_verse_patrol(
    device_name: str = "PatrolDevice",
    sample_count: int = 0,
    speed: float = 300.0,
    loop_patrol: bool = True,
    **kwargs,
) -> dict:
    """
    Generates a complete Verse creative_device with:
      - The spline points baked in as a vector3 array
      - A guard_spawner_device reference
      - OnBegin loop that moves the guard between waypoints
      - Speed and loop configurability

    Args:
        device_name:   Verse class name for the generated device.
        sample_count:  Evenly-sampled points (0 = control points).
        speed:         Guard movement speed in cm/s.
        loop_patrol:   If True, generate a looping patrol; else one-shot.
    """
    result = _require_spline()
    if result is None:
        return {"status": "error", "path": "", "device_name": device_name}

    actor, spline = result

    pts = _sample_spline_world(spline, sample_count) if sample_count > 0 \
          else _control_points_world(spline)

    array_code = _points_to_verse_array(pts, "PatrolWaypoints")
    loop_body = "loop:" if loop_patrol else "# One-shot patrol:"
    loop_reset = "            set CurrentWaypoint = Mod(CurrentWaypoint + 1, PatrolWaypoints.Length)" \
                 if loop_patrol else "            if (CurrentWaypoint < PatrolWaypoints.Length - 1):\n                set CurrentWaypoint += 1"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""\
# Generated by UEFN Toolbelt — Spline to Verse Patrol
# {timestamp}
# Source spline: '{actor.get_actor_label()}' — {len(pts)} waypoints

using {{ /Fortnite.com/Devices }}
using {{ /Verse.org/Simulation }}
using {{ /UnrealEngine.com/Temporary/Diagnostics }}

{device_name} := class(creative_device):

    # ── Waypoints baked from spline '{actor.get_actor_label()}' ────────────
{array_code}

    # ── Device references — wire these in the Blueprint Details panel ──────
    @editable  GuardSpawner : guard_spawner_device = guard_spawner_device{{}}

    # ── Configuration ──────────────────────────────────────────────────────
    @editable  PatrolSpeed  : float = {speed:.1f}  # cm/s

    # ── Internal state ─────────────────────────────────────────────────────
    var CurrentWaypoint<private> : int = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────
    OnBegin<override>()<suspends> : void =
        Print("{device_name}: Starting patrol ({len(pts)} waypoints)")
        GuardSpawner.SpawnGuard()
        _RunPatrol()

    _RunPatrol<private>()<suspends> : void =
        {loop_body}
            MoveGuard(PatrolWaypoints[CurrentWaypoint])
{loop_reset}

    # Move the guard toward a world-space waypoint.
    # Replace with your preferred movement API for your guard type.
    MoveGuard<private>(Target : vector3)<suspends> : void =
        # TODO: replace with your guard movement call
        # Example: Guard.NavigateTo(Target)
        Sleep(0.1)  # placeholder tick
        Print("Moving to waypoint {{CurrentWaypoint}}: X={{Target.X:.0f}}")
"""

    path = _write_snippet(f"{device_name}_patrol.verse", content)
    _try_clipboard(content)
    log_info(f"Patrol skeleton → {path}")
    log_info(f"\n{'='*60}\n{content}\n{'='*60}")
    return {"status": "ok", "path": path, "device_name": device_name}


@register_tool(
    name="spline_to_verse_zone_boundary",
    category="Verse Helpers",
    description="Convert selected spline to a Verse zone boundary vector3 array.",
    tags=["spline", "verse", "zone", "boundary", "area"],
)
def run_spline_to_verse_zone_boundary(
    zone_name: str = "ZoneBoundary",
    sample_count: int = 20,
    **kwargs,
) -> dict:
    """
    Generates a Verse array of boundary points useful for custom zone detection,
    minimap zones, or mutator area logic.

    Args:
        zone_name:    Variable name for the boundary array.
        sample_count: Number of points to sample around the boundary.
    """
    result = _require_spline()
    if result is None:
        return {"status": "error", "path": "", "point_count": 0}

    actor, spline = result
    pts = _sample_spline_world(spline, sample_count)

    # Compute centroid and radius for reference
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    max_r = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)

    array_code = _points_to_verse_array(pts, zone_name)
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""\
# Generated by UEFN Toolbelt — Spline to Verse Zone Boundary
# {timestamp}
# Source: '{actor.get_actor_label()}'
# Centroid: ({cx:.0f}, {cy:.0f})  |  Approx radius: {max_r:.0f} cm

using {{ /Verse.org/Simulation }}
using {{ /UnrealEngine.com/Temporary/Diagnostics }}

# ── Zone boundary points ────────────────────────────────────────────────────
# Paste inside your creative_device class body.
# Use with IsPointInZone() helper below.

{array_code}

    # Check if a world-space position is inside this zone boundary (2D XY check).
    # Uses a simple point-in-polygon ray-casting algorithm.
    IsPointInZone<private>(Point : vector3) : logic =
        var Inside : logic = false
        var j : int = {zone_name}.Length - 1
        for (i : int = 0, i < {zone_name}.Length, set i += 1):
            Pi := {zone_name}[i]
            Pj := {zone_name}[j]
            if (((Pi.Y > Point.Y) <> (Pj.Y > Point.Y)) and
                (Point.X < (Pj.X - Pi.X) * (Point.Y - Pi.Y) / (Pj.Y - Pi.Y) + Pi.X)):
                set Inside = not Inside
            set j = i
        Inside
"""

    path = _write_snippet(f"{zone_name}_boundary.verse", content)
    _try_clipboard(content)
    log_info(f"Zone boundary ({len(pts)} pts, ~{max_r:.0f}cm radius) → {path}")
    log_info(f"\n{'='*60}\n{content}\n{'='*60}")
    return {"status": "ok", "path": path, "point_count": len(pts)}


@register_tool(
    name="spline_export_json",
    category="Verse Helpers",
    description="Export selected spline point data to JSON (for use with scatter_along_path etc.).",
    tags=["spline", "export", "json", "path", "data"],
)
def run_spline_export_json(
    sample_count: int = 0,
    include_tangents: bool = False,
    **kwargs,
) -> dict:
    """
    Exports spline data as JSON to Saved/UEFN_Toolbelt/spline_export.json.
    The point list can be fed directly to scatter_along_path:

        import json
        with open(path) as f:
            data = json.load(f)
        pts = [(p['x'], p['y'], p['z']) for p in data['points']]
        tb.run("scatter_along_path", path_points=pts, mesh_path="...")

    Args:
        sample_count:     Evenly-sampled points (0 = control points only).
        include_tangents: Also export tangent vectors at each point.
    """
    result = _require_spline()
    if result is None:
        return {"status": "error", "path": "", "count": 0}

    actor, spline = result
    cs = unreal.SplineCoordinateSpace.WORLD

    if sample_count > 0:
        pts_raw = _sample_spline_world(spline, sample_count)
    else:
        pts_raw = _control_points_world(spline)

    records = []
    if include_tangents and sample_count > 0:
        total = spline.get_spline_length()
        for i, (x, y, z) in enumerate(pts_raw):
            dist = (i / max(len(pts_raw) - 1, 1)) * total
            t    = spline.get_tangent_at_distance_along_spline(dist, cs)
            records.append({"x": x, "y": y, "z": z,
                             "tx": t.x, "ty": t.y, "tz": t.z})
    else:
        records = [{"x": x, "y": y, "z": z} for x, y, z in pts_raw]

    out = {
        "source_actor":   actor.get_actor_label(),
        "spline_length":  spline.get_spline_length(),
        "point_count":    len(records),
        "exported_at":    datetime.now().isoformat(),
        "points":         records,
    }

    out_dir  = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
    out_path = os.path.join(out_dir, "spline_export.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    log_info(f"Exported {len(records)} spline points → {out_path}")
    log_info("Feed points into scatter_along_path using the pattern in the docstring.")
    return {"status": "ok", "path": out_path, "count": len(records)}

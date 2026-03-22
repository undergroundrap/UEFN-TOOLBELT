"""
UEFN TOOLBELT — Measurement Tools
========================================
Tools for spatial analysis, layout planning, and travel-time estimation.
Requested by the community for obby and obstacle course optimization.
"""

from __future__ import annotations

import math
from typing import List, Tuple, Optional

import unreal

from ..core import log_info, log_warning, log_error, get_selected_actors
from ..registry import register_tool

# ── Configuration ─────────────────────────────────────────────────────────────

# Standard Fortnite movement speeds (cm/s)
SPEEDS = {
    "Walk":   350.0,
    "Run":    450.0,
    "Sprint": 650.0,
}

# ─────────────────────────────────────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_distance(p1: unreal.Vector, p2: unreal.Vector) -> float:
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="measure_distance",
    category="Measurement",
    description="Measure the 3D distance between two selected actors or the total length of a chain of actors.",
    tags=["measure", "distance", "math", "layout"],
)
def run_measure_distance(**kwargs) -> float:
    actors = get_selected_actors()
    if len(actors) < 2:
        log_warning("Select at least 2 actors to measure distance.")
        return 0.0

    total_dist = 0.0
    for i in range(len(actors) - 1):
        p1 = actors[i].get_actor_location()
        p2 = actors[i+1].get_actor_location()
        total_dist += _get_distance(p1, p2)

    log_info(f"Total Distance: {total_dist:.2f} cm")
    return total_dist


@register_tool(
    name="measure_travel_time",
    category="Measurement",
    description="Calculate the time (sec) it takes to travel between selected points at specific speeds.",
    tags=["measure", "time", "travel", "obby"],
)
def run_measure_travel_time(speed_type: str = "Run", custom_speed: float = 0.0, **kwargs) -> dict:
    actors = get_selected_actors()
    if len(actors) < 2:
        log_warning("Select at least 2 actors to measure travel time.")
        return {}

    dist = run_measure_distance()
    actual_speed = custom_speed if custom_speed > 0 else SPEEDS.get(speed_type, SPEEDS["Run"])

    time_sec = dist / actual_speed
    
    log_info(f"Travel Time ({speed_type} @ {actual_speed}cm/s): {time_sec:.2f} seconds")
    
    return {
        "distance": dist,
        "speed": actual_speed,
        "time_seconds": time_sec
    }


@register_tool(
    name="spline_measure",
    category="Measurement",
    description="Get the total world-space length of a selected spline actor.",
    tags=["spline", "measure", "length"],
)
def run_spline_measure(**kwargs) -> float:
    actors = get_selected_actors()
    if not actors:
        log_warning("Select a spline actor.")
        return 0.0

    spline = None
    for actor in actors:
        comps = actor.get_components_by_class(unreal.SplineComponent.static_class())
        if comps:
            spline = comps[0]
            break

    if not spline:
        log_error("No SplineComponent found on selection.")
        return 0.0

    length = spline.get_spline_length()
    log_info(f"Spline Length: {length:.2f} cm")
    return length

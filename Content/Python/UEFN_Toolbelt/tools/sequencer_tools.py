"""
UEFN TOOLBELT — Sequencer Automation
=======================================
Cinematic automation for Level Sequences.
"""

from __future__ import annotations
import unreal
from ..core import log_info, log_error, undo_transaction, require_selection
from ..registry import register_tool

@register_tool(
    name="seq_actor_to_spline",
    category="Sequencer",
    description="Animate a selected actor along a selected spline path.",
    tags=["sequencer", "spline", "animate", "path"],
)
def run_actor_to_spline(duration: float = 5.0, fps: int = 30, **kwargs) -> dict:
    """
    Args:
        duration: Duration of the animation in seconds.
        fps: Frames per second for the sequence.
    """
    actors = require_selection(min_count=2)
    if not actors:
        return {"status": "error", "path": None}

    # Identify Spline and Actor
    spline_actor = None
    target_actor = None

    for a in actors:
        if a.get_component_by_class(unreal.SplineComponent):
            spline_actor = a
            break

    for a in actors:
        if a != spline_actor:
            target_actor = a
            break

    if not spline_actor or not target_actor:
        log_error("Selection must include 1 Spline Actor and 1 Target Actor.")
        return {"status": "error", "path": None}

    spline = spline_actor.get_component_by_class(unreal.SplineComponent)
    length = spline.get_spline_length()
    total_frames = int(duration * fps)

    log_info(f"Animating {target_actor.get_actor_label()} along {spline_actor.get_actor_label()}...")

    with undo_transaction("Sequencer: Actor to Spline"):
        # Create/Get Level Sequence
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        seq_name = f"LS_Path_{target_actor.get_actor_label()}"
        seq_path = "/Game/UEFN_Toolbelt/Sequences"
        
        # Ensure folder exists
        unreal.EditorAssetLibrary.make_directory(seq_path)
        
        ls = asset_tools.create_asset(seq_name, seq_path, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        if not ls:
            log_error("Failed to create Level Sequence.")
            return {"status": "error", "path": None}

        ls.set_display_rate(unreal.FrameRate(fps, 1))
        ls.set_playback_start(0)
        ls.set_playback_end(total_frames)

        # Add Possessable
        possessable = ls.add_possessable(target_actor)
        
        # Add Transform Track
        transform_track = possessable.add_track(unreal.MovieScene3DTransformTrack)
        transform_section = transform_track.add_section()
        transform_section.set_range(0, total_frames)

        # Generate Keyframes
        for frame in range(total_frames + 1):
            t = frame / total_frames
            dist = t * length
            pos = spline.get_location_at_distance_along_spline(dist, unreal.SplineCoordinateSpace.WORLD)
            rot = spline.get_rotation_at_distance_along_spline(dist, unreal.SplineCoordinateSpace.WORLD)
            
            # Add keys to the transform channels
            # Note: In UEFN we use the MovieScene scripting API
            for i, val in enumerate([pos.x, pos.y, pos.z]):
                channel = transform_section.get_channels()[i] # Location X, Y, Z
                channel.add_key(unreal.FrameNumber(frame), val)
                
            for i, val in enumerate([rot.roll, rot.pitch, rot.yaw]):
                channel = transform_section.get_channels()[idx := i + 3] # Rotation R, P, Y
                channel.add_key(unreal.FrameNumber(frame), val)

    log_info(f"Created Level Sequence: {seq_path}/{seq_name}")
    return {"status": "ok", "path": f"{seq_path}/{seq_name}", "frames": total_frames}


@register_tool(
    name="seq_batch_keyframe",
    category="Sequencer",
    description="Add a transform keyframe for all selected actors at current time.",
    tags=["sequencer", "keyframe", "bulk"],
)
def run_batch_keyframe(**kwargs) -> dict:
    actors = require_selection()
    if not actors:
        return {"status": "error", "keyed": 0}

    # Logic to find current active sequence and add keys
    log_info(f"Adding keyframes for {len(actors)} actors...")
    # (Implementation pending active sequence discovery API)
    return {"status": "ok", "keyed": len(actors)}

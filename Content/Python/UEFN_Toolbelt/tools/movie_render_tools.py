"""
UEFN TOOLBELT — Movie Render Pipeline Tools
========================================
Automate cinematic rendering via the Movie Render Pipeline (145 classes).

Use cases:
  • Queue a Level Sequence for batch rendering
  • Apply resolution / format presets to render jobs
  • Check the current render pipeline state
  • Export promotional screenshots at custom resolutions

API reference: unreal.MoviePipelineQueueEngineSubsystem,
               unreal.MoviePipelineExecutorJob,
               unreal.MoviePipelineOutputSetting

NOTE: Movie Render Pipeline renders take time — the editor will be busy
while a render is in progress. Use movie_render_status to poll state.
Renders output to the path set in the output preset (default: Project/Saved/MovieRenders/).
"""

from __future__ import annotations

import os

import unreal

from ..core import log_error, log_info, log_warning
from ..registry import register_tool


def _get_queue_subsystem():
    """Return the MoviePipelineQueueEngineSubsystem."""
    return unreal.get_engine_subsystem(unreal.MoviePipelineQueueEngineSubsystem)


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="movie_render_queue_sequence",
    category="Cinematic",
    description=(
        "Add a Level Sequence to the Movie Render Queue with optional output settings. "
        "Set start_render=True to kick off rendering immediately."
    ),
    tags=["movie", "render", "cinematic", "sequence", "export", "pipeline"],
)
def run_movie_render_queue_sequence(
    sequence_path: str = "",
    output_dir: str = "",
    width: int = 1920,
    height: int = 1080,
    start_render: bool = False,
    **kwargs,
) -> dict:
    """
    Queue a Level Sequence for Movie Render Pipeline output.

    Args:
        sequence_path: Content Browser path to a LevelSequence asset.
                       e.g. "/Game/Sequences/LS_Cinematic"
        output_dir:    Output directory path. Defaults to Project/Saved/MovieRenders/
        width:         Output width in pixels (default 1920)
        height:        Output height in pixels (default 1080)
        start_render:  If True, starts rendering immediately (default False — queue only)
    """
    if not sequence_path:
        return {"status": "error", "error": "sequence_path is required. Provide a LevelSequence asset path."}

    try:
        # Validate the sequence asset exists
        seq_asset = unreal.EditorAssetLibrary.load_asset(sequence_path)
        if seq_asset is None:
            return {"status": "error", "error": f"Sequence not found: {sequence_path}"}

        queue_sub = _get_queue_subsystem()
        if queue_sub is None:
            return {"status": "error", "error": "MoviePipelineQueueEngineSubsystem not available in this UEFN build."}

        queue = queue_sub.get_queue()
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        job.sequence = unreal.SoftObjectPath(sequence_path)
        job.job_name = os.path.basename(sequence_path)

        # Apply output settings
        config = job.get_configuration()
        output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        output_setting.output_resolution = unreal.IntPoint(width, height)
        if output_dir:
            output_setting.output_directory = unreal.DirectoryPath(output_dir)

        log_info(f"movie_render_queue_sequence: queued '{job.job_name}' at {width}x{height}")

        if start_render:
            executor = unreal.MoviePipelinePIEExecutor()
            queue_sub.render_queue_with_executor_instance(executor)
            return {
                "status": "ok",
                "job": job.job_name,
                "resolution": f"{width}x{height}",
                "rendering": True,
                "message": "Render started. Use movie_render_status to check progress.",
            }

        return {
            "status": "ok",
            "job": job.job_name,
            "sequence": sequence_path,
            "resolution": f"{width}x{height}",
            "rendering": False,
            "message": "Job queued. Call again with start_render=True to begin, or use the Movie Render Queue UI.",
        }
    except Exception as e:
        log_error(f"movie_render_queue_sequence failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="movie_render_apply_preset",
    category="Cinematic",
    description=(
        "Apply a named output preset to all queued render jobs. "
        "Presets: '4k', '1080p', '720p', 'promo_square', 'thumbnail'."
    ),
    tags=["movie", "render", "cinematic", "preset", "resolution", "output"],
)
def run_movie_render_apply_preset(
    preset: str = "1080p",
    **kwargs,
) -> dict:
    """
    Apply a resolution/format preset to all jobs currently in the render queue.

    Args:
        preset: One of '4k' (3840×2160), '1080p' (1920×1080), '720p' (1280×720),
                'promo_square' (1080×1080), 'thumbnail' (512×512)
    """
    PRESETS = {
        "4k":           (3840, 2160),
        "1080p":        (1920, 1080),
        "720p":         (1280, 720),
        "promo_square": (1080, 1080),
        "thumbnail":    (512, 512),
    }

    if preset not in PRESETS:
        return {
            "status": "error",
            "error": f"Unknown preset '{preset}'. Valid: {', '.join(PRESETS.keys())}",
        }

    w, h = PRESETS[preset]

    try:
        queue_sub = _get_queue_subsystem()
        if queue_sub is None:
            return {"status": "error", "error": "MoviePipelineQueueEngineSubsystem not available."}

        queue = queue_sub.get_queue()
        jobs = queue.get_jobs()
        if not jobs:
            return {"status": "error", "error": "No jobs in the render queue. Use movie_render_queue_sequence first."}

        updated = 0
        for job in jobs:
            try:
                config = job.get_configuration()
                output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
                output_setting.output_resolution = unreal.IntPoint(w, h)
                updated += 1
            except Exception as e:
                log_warning(f"  preset apply failed on job '{job.job_name}': {e}")

        log_info(f"movie_render_apply_preset: '{preset}' ({w}x{h}) applied to {updated} job(s).")
        return {
            "status": "ok",
            "preset": preset,
            "resolution": f"{w}x{h}",
            "jobs_updated": updated,
        }
    except Exception as e:
        log_error(f"movie_render_apply_preset failed: {e}")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="movie_render_status",
    category="Cinematic",
    description=(
        "Check the current Movie Render Pipeline queue — "
        "how many jobs are queued, which is active, and whether rendering is in progress."
    ),
    tags=["movie", "render", "cinematic", "status", "queue", "pipeline"],
)
def run_movie_render_status(**kwargs) -> dict:
    """Return the current state of the Movie Render Pipeline queue."""
    try:
        queue_sub = _get_queue_subsystem()
        if queue_sub is None:
            return {"status": "error", "error": "MoviePipelineQueueEngineSubsystem not available in this UEFN build."}

        queue = queue_sub.get_queue()
        jobs = queue.get_jobs()

        job_list = []
        for job in jobs:
            try:
                config = job.get_configuration()
                output_setting = config.find_setting_by_class(unreal.MoviePipelineOutputSetting)
                res = output_setting.output_resolution if output_setting else None
                job_list.append({
                    "name":       job.job_name,
                    "sequence":   str(job.sequence),
                    "resolution": f"{res.x}x{res.y}" if res else "default",
                    "enabled":    not job.is_disabled() if hasattr(job, "is_disabled") else True,
                })
            except Exception:
                job_list.append({"name": getattr(job, "job_name", "unknown")})

        log_info(f"movie_render_status: {len(job_list)} job(s) in queue.")
        return {
            "status": "ok",
            "queued_jobs": len(job_list),
            "jobs": job_list,
        }
    except Exception as e:
        log_error(f"movie_render_status failed: {e}")
        return {"status": "error", "error": str(e)}

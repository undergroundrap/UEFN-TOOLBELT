"""
UEFN TOOLBELT — Sound Asset Tools
=====================================
Tools for inspecting and auditing sound assets in the Content Browser.
Complements audio_tools (which manages AmbientSound level actors) by covering
the asset side: SoundWave, SoundCue, SoundAttenuation, and SoundClass.

What Python CAN do:
  • List all SoundWave / SoundCue assets in a folder
  • Audit SoundWave assets for missing SoundClass or long duration
  • List all SoundAttenuation settings assets
  • List all SoundClass assets

What Python CANNOT do:
  • Edit SoundWave audio data (binary waveform is read-only)
  • Create or edit SoundCue node graphs (graph editing is UI-only)
  • Modify MetaSound node graphs
  • Set SoundAttenuation falloff curves programmatically

API: AssetRegistry, EditorAssetLibrary, SoundWave, SoundCue, SoundAttenuation, SoundClass
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, log_warning
from ..registry import register_tool


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


_SOUND_CLASSES = ["SoundWave", "SoundCue"]


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="sound_asset_list",
    category="Sound Assets",
    description=(
        "List all SoundWave and SoundCue assets in a Content Browser folder. "
        "Returns asset paths, class type, duration, channel count, and sample rate. "
        "Use sound_type to filter: 'wave', 'cue', or 'all'."
    ),
    tags=["sound", "audio", "list", "assets", "scan"],
    example='tb.run("sound_asset_list", scan_path="/Game/Audio", sound_type="wave")',
)
def run_sound_asset_list(
    scan_path: str = "/Game/",
    sound_type: str = "all",
    max_results: int = 200,
    **kwargs,
) -> dict:
    try:
        type_map = {
            "wave": ["SoundWave"],
            "cue":  ["SoundCue"],
            "all":  _SOUND_CLASSES,
        }
        class_filter = type_map.get(sound_type.lower(), _SOUND_CLASSES)
        filt = unreal.ARFilter(
            class_names=class_filter,
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = []
        for a in assets:
            results.append({
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "type": str(a.asset_class),
                "duration": a.get_tag_value("Duration"),
                "channels": a.get_tag_value("NumChannels"),
                "sample_rate": a.get_tag_value("SampleRateOverride") or a.get_tag_value("SampleRate"),
            })
        log_info(f"[sound_asset_list] {len(results)} sound asset(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "sounds": results}
    except Exception as e:
        log_error(f"[sound_asset_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="sound_asset_audit",
    category="Sound Assets",
    description=(
        "Audit SoundWave assets in a folder for common issues: "
        "missing SoundClass assignment or duration exceeding the warn threshold. "
        "Returns a health report useful for audio budget and mixing reviews."
    ),
    tags=["sound", "audio", "audit", "health", "quality", "soundclass"],
    example='tb.run("sound_asset_audit", scan_path="/Game/Audio", warn_duration_sec=60)',
)
def run_sound_asset_audit(
    scan_path: str = "/Game/",
    warn_duration_sec: float = 60.0,
    max_results: int = 200,
    **kwargs,
) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["SoundWave"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        issues = []
        clean = []

        for a in assets:
            name = str(a.asset_name)
            path = str(a.package_name)
            sound_issues = []

            # Duration check via AR tag (no load needed)
            duration_tag = a.get_tag_value("Duration")
            try:
                if duration_tag and float(duration_tag) > warn_duration_sec:
                    sound_issues.append(
                        f"Long duration: {float(duration_tag):.1f}s (warn={warn_duration_sec}s)"
                    )
            except (ValueError, TypeError):
                pass

            # SoundClass check requires load (only 1 prop read per asset)
            try:
                sw = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if isinstance(sw, unreal.SoundWave):
                    try:
                        sc = sw.get_editor_property("sound_class_object")
                        if sc is None:
                            sound_issues.append("No SoundClass assigned")
                    except Exception:
                        pass
            except Exception as ex:
                log_warning(f"[sound_asset_audit] {name}: could not load — {ex}")

            if sound_issues:
                issues.append({"name": name, "path": path, "issues": sound_issues})
            else:
                clean.append(name)

        log_info(f"[sound_asset_audit] {len(clean)} clean, {len(issues)} issues in {scan_path}")
        return {
            "status": "ok",
            "total": len(assets),
            "clean": len(clean),
            "issues": len(issues),
            "issue_list": issues,
        }
    except Exception as e:
        log_error(f"[sound_asset_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="sound_attenuation_list",
    category="Sound Assets",
    description=(
        "List all SoundAttenuation assets in a folder. "
        "SoundAttenuation defines falloff curves and spatialization for 3D audio. "
        "Returns asset paths — use to audit which attenuation presets exist in the project."
    ),
    tags=["sound", "attenuation", "audio", "list", "3d", "spatial"],
    example='tb.run("sound_attenuation_list", scan_path="/Game/Audio")',
)
def run_sound_attenuation_list(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["SoundAttenuation"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = [
            {"name": str(a.asset_name), "path": str(a.package_name)}
            for a in assets
        ]
        log_info(f"[sound_attenuation_list] {len(results)} SoundAttenuation asset(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "attenuation_assets": results}
    except Exception as e:
        log_error(f"[sound_attenuation_list] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="sound_class_list",
    category="Sound Assets",
    description=(
        "List all SoundClass assets in a folder. "
        "SoundClass controls volume, pitch, and bus routing for groups of sounds. "
        "Use this to audit your audio mixing hierarchy."
    ),
    tags=["sound", "class", "audio", "list", "mix", "routing"],
    example='tb.run("sound_class_list", scan_path="/Game/Audio")',
)
def run_sound_class_list(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    try:
        filt = unreal.ARFilter(
            class_names=["SoundClass"],
            package_paths=[scan_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filt)[:max_results]
        results = [
            {"name": str(a.asset_name), "path": str(a.package_name)}
            for a in assets
        ]
        log_info(f"[sound_class_list] {len(results)} SoundClass asset(s) in {scan_path}")
        return {"status": "ok", "count": len(results), "sound_classes": results}
    except Exception as e:
        log_error(f"[sound_class_list] {e}")
        return {"status": "error", "message": str(e)}

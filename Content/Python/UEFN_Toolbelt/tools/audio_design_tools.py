"""
UEFN TOOLBELT — Audio Design Tools
=====================================
Tools for MetaSound, SoundClass, SoundCue, SoundMix, and AudioSynesthesia.

AudioMixer (36), MetasoundEngine (24), MetasoundEditor (37),
Synthesis (126), AudioSynesthesia (38)

What Python CAN do:
  • List MetaSoundSource, MetaSoundPatch, SoundCue, SoundClass, SoundMix assets
  • Inspect SoundClass volume/pitch group properties
  • List AudioSynesthesia analyzers (loudness, onset, constant-Q)
  • Inspect MetaSound asset editor properties (autoplay, quality level)
  • Batch-set autoplay on MetaSound assets

What Python CANNOT do:
  • Edit MetaSound node graphs (graph is a Blueprint-only editor UI)
  • Create audio buses from scratch (factory not exposed)
  • Trigger Quartz clocks from Python (game-world subsystem, not editor)
  • Build SoundCue node graphs programmatically

API: MetasoundEngine, MetasoundEditor, AudioMixer, Synthesis, AudioSynesthesia
"""

from __future__ import annotations

import unreal

from ..core import log_error, log_info, resolve_scan_path
from ..registry import register_tool


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="audio_list_metasounds",
    category="Audio",
    description=(
        "List all MetaSoundSource and MetaSoundPatch assets in the project. "
        "MetaSounds are graph-based procedural audio assets that replace SoundCues "
        "for complex synthesis and DSP chains."
    ),
    tags=["audio", "metasound", "list", "synthesis", "sound", "dsp"],
    example='tb.run("audio_list_metasounds", search_path="/Game/")',
)
def run_audio_list_metasounds(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["MetaSoundSource", "MetaSoundPatch"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = []
        for a in assets:
            entry = {"name": str(a.asset_name), "path": str(a.package_name), "class": str(a.asset_class)}
            try:
                loaded = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if loaded:
                    autoplay = loaded.get_editor_property("b_auto_play") if hasattr(loaded, "get_editor_property") else None
                    if autoplay is not None:
                        entry["autoplay"] = autoplay
            except Exception:
                pass
            results.append(entry)
        log_info(f"[audio_list_metasounds] {len(results)} MetaSound assets in {search_path}")
        return {"status": "ok", "count": len(results), "metasounds": results}
    except Exception as e:
        log_error(f"[audio_list_metasounds] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="audio_list_sound_classes",
    category="Audio",
    description=(
        "List all SoundClass assets. SoundClasses define named volume/pitch "
        "groups for mixing (e.g. Music, SFX, Voice, Ambience). "
        "Returns name, path, and volume multiplier."
    ),
    tags=["audio", "sound", "class", "mix", "group", "list"],
    example='tb.run("audio_list_sound_classes")',
)
def run_audio_list_sound_classes(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["SoundClass"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = []
        for a in assets:
            entry = {"name": str(a.asset_name), "path": str(a.package_name)}
            try:
                loaded = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if loaded:
                    props = loaded.get_editor_property("properties")
                    if props:
                        entry["volume"] = props.get_editor_property("volume")
                        entry["pitch"]  = props.get_editor_property("pitch")
            except Exception:
                pass
            results.append(entry)
        log_info(f"[audio_list_sound_classes] {len(results)} SoundClass assets")
        return {"status": "ok", "count": len(results), "sound_classes": results}
    except Exception as e:
        log_error(f"[audio_list_sound_classes] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="audio_list_sound_cues",
    category="Audio",
    description=(
        "List all SoundCue assets. SoundCues are modular audio graphs with "
        "random, loop, mix, and sequence nodes — the legacy equivalent of MetaSound."
    ),
    tags=["audio", "cue", "sound", "list", "sfx", "legacy"],
    example='tb.run("audio_list_sound_cues", search_path="/Game/Audio/")',
)
def run_audio_list_sound_cues(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["SoundCue"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [{"name": str(a.asset_name), "path": str(a.package_name)} for a in assets]
        log_info(f"[audio_list_sound_cues] {len(results)} SoundCue assets in {search_path}")
        return {"status": "ok", "count": len(results), "sound_cues": results}
    except Exception as e:
        log_error(f"[audio_list_sound_cues] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="audio_list_sound_mixes",
    category="Audio",
    description=(
        "List all SoundMix assets. SoundMixes are snapshots that adjust "
        "SoundClass volumes and pitches at runtime — used for music ducking, "
        "pause menu attenuation, and cinematic mix states."
    ),
    tags=["audio", "mix", "sound", "ducking", "snapshot", "list"],
    example='tb.run("audio_list_sound_mixes")',
)
def run_audio_list_sound_mixes(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["SoundMix"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [{"name": str(a.asset_name), "path": str(a.package_name)} for a in assets]
        log_info(f"[audio_list_sound_mixes] {len(results)} SoundMix assets")
        return {"status": "ok", "count": len(results), "sound_mixes": results}
    except Exception as e:
        log_error(f"[audio_list_sound_mixes] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="audio_list_synesthesia",
    category="Audio",
    description=(
        "List all AudioSynesthesia analyzer assets (LoudnessNRT, ConstantQNRT, "
        "OnsetNRT). AudioSynesthesia extracts frequency, loudness, and onset "
        "data from SoundWaves — used for visualizers and rhythm-sync effects."
    ),
    tags=["audio", "synesthesia", "analysis", "loudness", "onset", "frequency", "list"],
    example='tb.run("audio_list_synesthesia")',
)
def run_audio_list_synesthesia(search_path: str = "", **kwargs) -> dict:
    search_path = resolve_scan_path(search_path)
    try:
        filter_ = unreal.ARFilter(
            class_names=["LoudnessNRT", "ConstantQNRT", "OnsetNRT"],
            package_paths=[search_path],
            recursive_paths=True,
        )
        assets = _ar().get_assets(filter_)
        results = [
            {"name": str(a.asset_name), "path": str(a.package_name), "class": str(a.asset_class)}
            for a in assets
        ]
        log_info(f"[audio_list_synesthesia] {len(results)} AudioSynesthesia analyzers in {search_path}")
        return {"status": "ok", "count": len(results), "analyzers": results}
    except Exception as e:
        log_error(f"[audio_list_synesthesia] {e}")
        return {"status": "error", "message": str(e)}

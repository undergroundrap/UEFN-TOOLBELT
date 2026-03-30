"""
UEFN TOOLBELT — Texture Editing Tools
=======================================
Tools for reading and writing texture settings on Texture2D assets.

Complements memory_scan_textures (which REPORTS oversized textures) by
providing tools that actually FIX them — setting compression, mip generation,
texture groups, and sRGB flags in bulk.

What Python CAN do:
  • Read compression settings, texture group, sRGB, mip gen settings
  • Set TextureCompressionSettings on selected or folder textures
  • Set TextureGroup on a batch of textures
  • Toggle sRGB on a batch of textures
  • Apply sensible presets (game / ui / normal / hdr)

What Python CANNOT do:
  • Re-compress source art (read-only source data)
  • Create Texture2D assets from raw pixel data via Python
  • Modify virtual texture settings (VT streaming is editor-only UI)

API: EditorAssetLibrary, AssetRegistry, Texture2D editor properties
"""

from __future__ import annotations

import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


def _load_textures_in_folder(scan_path: str) -> list:
    """Return all Texture2D assets under scan_path."""
    filt = unreal.ARFilter(
        class_names=["Texture2D"],
        package_paths=[scan_path],
        recursive_paths=True,
    )
    return _ar().get_assets(filt)


# ── Compression setting name → enum mapping ──────────────────────────────────

_COMPRESSION_MAP = {
    "TC_DEFAULT":          "TC_DEFAULT",
    "TC_NORMALMAP":        "TC_NORMALMAP",
    "TC_MASKS":            "TC_MASKS",
    "TC_GRAYSCALE":        "TC_GRAYSCALE",
    "TC_ALPHA":            "TC_ALPHA",
    "TC_HDR":              "TC_HDR",
    "TC_BC7":              "TC_BC7",
    "TC_USERINTERFACE2D":  "TC_UserInterface2D",
    "TC_UI":               "TC_UserInterface2D",
}

_TEXTURE_GROUP_MAP = {
    "world":            "TEXTUREGROUP_World",
    "world_normalmap":  "TEXTUREGROUP_WorldNormalMap",
    "character":        "TEXTUREGROUP_Character",
    "ui":               "TEXTUREGROUP_UI",
    "lightmap":         "TEXTUREGROUP_Lightmap",
    "effects":          "TEXTUREGROUP_Effects",
    "skybox":           "TEXTUREGROUP_Skybox",
    "vehicle":          "TEXTUREGROUP_Vehicle",
    "weapon":           "TEXTUREGROUP_Weapon",
    "cinematic":        "TEXTUREGROUP_Cinematic",
}

# Presets: (compression, texture_group, srgb, mip_gen)
_PRESETS = {
    "game":     ("TC_DEFAULT",          "world",      True,  "TMGS_FromTextureGroup"),
    "ui":       ("TC_UserInterface2D",  "ui",         True,  "TMGS_NoMipmaps"),
    "normal":   ("TC_NORMALMAP",        "world_normalmap", False, "TMGS_FromTextureGroup"),
    "mask":     ("TC_MASKS",            "world",      False, "TMGS_FromTextureGroup"),
    "hdr":      ("TC_HDR",              "world",      False, "TMGS_FromTextureGroup"),
    "icon":     ("TC_UserInterface2D",  "ui",         True,  "TMGS_NoMipmaps"),
    "grayscale":("TC_GRAYSCALE",        "world",      False, "TMGS_FromTextureGroup"),
}


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="texture_audit",
    category="Textures",
    description=(
        "Audit all Texture2D assets in a folder — lists compression setting, "
        "texture group, sRGB flag, and mip gen mode for each texture. "
        "Use this to find misconfigured textures before optimizing."
    ),
    tags=["texture", "audit", "compression", "settings", "scan"],
    example='tb.run("texture_audit", scan_path="/Game/Textures")',
)
def run_texture_audit(scan_path: str = "/Game/", max_results: int = 200, **kwargs) -> dict:
    # Uses AR tag data only — never calls load_asset(), safe on pak-heavy projects.
    try:
        assets = _load_textures_in_folder(scan_path)[:max_results]
        results = []
        for a in assets:
            entry = {
                "name": str(a.asset_name),
                "path": str(a.package_name),
                "compression": str(a.get_tag_value("CompressionSettings") or "unknown"),
                "texture_group": str(a.get_tag_value("LODGroup") or "unknown"),
                "srgb": a.get_tag_value("SRGB"),
                "size_x": a.get_tag_value("SizeX"),
                "size_y": a.get_tag_value("SizeY"),
            }
            results.append(entry)

        log_info(f"[texture_audit] {len(results)} textures audited in {scan_path}")
        return {"status": "ok", "count": len(results), "textures": results}
    except Exception as e:
        log_error(f"[texture_audit] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="texture_set_compression",
    category="Textures",
    description=(
        "Batch-set TextureCompressionSettings on textures in a folder. "
        "Valid compression values: TC_DEFAULT, TC_NORMALMAP, TC_MASKS, TC_GRAYSCALE, "
        "TC_ALPHA, TC_HDR, TC_BC7, TC_UI (alias for TC_UserInterface2D). "
        "Always dry_run=True first to preview which textures will change."
    ),
    tags=["texture", "compression", "batch", "set"],
    example='tb.run("texture_set_compression", scan_path="/Game/Textures/Normal", compression="TC_NORMALMAP", dry_run=False)',
)
def run_texture_set_compression(
    scan_path: str = "/Game/",
    compression: str = "TC_DEFAULT",
    dry_run: bool = True,
    max_assets: int = 500,
    **kwargs,
) -> dict:
    try:
        assets = _load_textures_in_folder(scan_path)
        compression_upper = compression.upper()
        if compression_upper not in _COMPRESSION_MAP:
            valid = list(_COMPRESSION_MAP.keys())
            return {"status": "error", "message": f"Unknown compression '{compression}'. Valid: {valid}"}

        compression_value = _COMPRESSION_MAP[compression_upper]
        assets = assets[:max_assets]
        changed = []
        skipped = []

        for a in assets:
            try:
                tex = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(tex, unreal.Texture2D):
                    continue
                current = str(tex.get_editor_property("compression_settings"))
                if current == compression_value:
                    skipped.append(str(a.asset_name))
                    continue
                if not dry_run:
                    comp_enum = getattr(unreal.TextureCompressionSettings, compression_value, None)
                    if comp_enum is not None:
                        tex.set_editor_property("compression_settings", comp_enum)
                        unreal.EditorAssetLibrary.save_loaded_asset(tex)
                changed.append({"name": str(a.asset_name), "from": current, "to": compression_value})
            except Exception as ex:
                log_warning(f"[texture_set_compression] {a.asset_name}: {ex}")

        action = "Would change" if dry_run else "Changed"
        log_info(f"[texture_set_compression] {action} {len(changed)} textures in {scan_path}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "compression": compression_value,
            "changed": len(changed),
            "skipped": len(skipped),
            "changes": changed,
        }
    except Exception as e:
        log_error(f"[texture_set_compression] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="texture_set_group",
    category="Textures",
    description=(
        "Batch-set the TextureGroup (LOD group) on textures in a folder. "
        "Valid groups: world, world_normalmap, character, ui, lightmap, effects, skybox, weapon, vehicle, cinematic. "
        "TextureGroup controls mip streaming budget and quality tier."
    ),
    tags=["texture", "group", "lod", "batch", "set"],
    example='tb.run("texture_set_group", scan_path="/Game/UI/Icons", group="ui", dry_run=False)',
)
def run_texture_set_group(
    scan_path: str = "/Game/",
    group: str = "world",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    try:
        assets = _load_textures_in_folder(scan_path)
        group_lower = group.lower()
        if group_lower not in _TEXTURE_GROUP_MAP:
            valid = list(_TEXTURE_GROUP_MAP.keys())
            return {"status": "error", "message": f"Unknown group '{group}'. Valid: {valid}"}

        group_value = _TEXTURE_GROUP_MAP[group_lower]
        changed = []
        skipped = []

        for a in assets:
            try:
                tex = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(tex, unreal.Texture2D):
                    continue
                current = str(tex.get_editor_property("lod_group"))
                if current == group_value:
                    skipped.append(str(a.asset_name))
                    continue
                if not dry_run:
                    group_enum = getattr(unreal.TextureGroup, group_value, None)
                    if group_enum is not None:
                        tex.set_editor_property("lod_group", group_enum)
                        unreal.EditorAssetLibrary.save_loaded_asset(tex)
                changed.append({"name": str(a.asset_name), "from": current, "to": group_value})
            except Exception as ex:
                log_warning(f"[texture_set_group] {a.asset_name}: {ex}")

        action = "Would change" if dry_run else "Changed"
        log_info(f"[texture_set_group] {action} {len(changed)} textures in {scan_path}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "group": group_value,
            "changed": len(changed),
            "skipped": len(skipped),
            "changes": changed,
        }
    except Exception as e:
        log_error(f"[texture_set_group] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="texture_set_srgb",
    category="Textures",
    description=(
        "Batch-set the sRGB flag on textures in a folder. "
        "sRGB=True for albedo/diffuse color textures. "
        "sRGB=False for normal maps, masks, roughness, metalness, and data textures. "
        "Incorrect sRGB settings cause color-space errors in materials."
    ),
    tags=["texture", "srgb", "color", "batch", "set"],
    example='tb.run("texture_set_srgb", scan_path="/Game/Textures/Normals", srgb=False, dry_run=False)',
)
def run_texture_set_srgb(
    scan_path: str = "/Game/",
    srgb: bool = True,
    dry_run: bool = True,
    **kwargs,
) -> dict:
    try:
        assets = _load_textures_in_folder(scan_path)
        changed = []
        skipped = []

        for a in assets:
            try:
                tex = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(tex, unreal.Texture2D):
                    continue
                current = tex.get_editor_property("srgb")
                if current == srgb:
                    skipped.append(str(a.asset_name))
                    continue
                if not dry_run:
                    tex.set_editor_property("srgb", srgb)
                    unreal.EditorAssetLibrary.save_loaded_asset(tex)
                changed.append({"name": str(a.asset_name), "from": current, "to": srgb})
            except Exception as ex:
                log_warning(f"[texture_set_srgb] {a.asset_name}: {ex}")

        action = "Would change" if dry_run else "Changed"
        log_info(f"[texture_set_srgb] {action} {len(changed)} textures in {scan_path}")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "srgb": srgb,
            "changed": len(changed),
            "skipped": len(skipped),
            "changes": changed,
        }
    except Exception as e:
        log_error(f"[texture_set_srgb] {e}")
        return {"status": "error", "message": str(e)}


@register_tool(
    name="texture_apply_preset",
    category="Textures",
    description=(
        "Apply a named texture preset to all Texture2D assets in a folder. "
        "Presets set compression + texture group + sRGB + mip gen in one call. "
        "Presets: game, ui, normal, mask, hdr, icon, grayscale. "
        "Always dry_run=True first — this changes multiple settings at once."
    ),
    tags=["texture", "preset", "batch", "compression", "fix"],
    example='tb.run("texture_apply_preset", scan_path="/Game/Textures/UI", preset="ui", dry_run=False)',
)
def run_texture_apply_preset(
    scan_path: str = "/Game/",
    preset: str = "game",
    dry_run: bool = True,
    **kwargs,
) -> dict:
    preset_lower = preset.lower()
    if preset_lower not in _PRESETS:
        return {"status": "error", "message": f"Unknown preset '{preset}'. Valid: {list(_PRESETS.keys())}"}

    compression_str, group_str, srgb_val, mip_str = _PRESETS[preset_lower]

    try:
        assets = _load_textures_in_folder(scan_path)
        changed = 0
        errors = []

        for a in assets:
            try:
                tex = unreal.EditorAssetLibrary.load_asset(str(a.object_path))
                if not isinstance(tex, unreal.Texture2D):
                    continue
                if not dry_run:
                    comp_enum = getattr(unreal.TextureCompressionSettings, compression_str, None)
                    group_enum = getattr(unreal.TextureGroup, _TEXTURE_GROUP_MAP.get(group_str, group_str), None)
                    mip_enum = getattr(unreal.TextureMipGenSettings, mip_str, None)

                    if comp_enum is not None:
                        tex.set_editor_property("compression_settings", comp_enum)
                    if group_enum is not None:
                        tex.set_editor_property("lod_group", group_enum)
                    tex.set_editor_property("srgb", srgb_val)
                    if mip_enum is not None:
                        tex.set_editor_property("mip_gen_settings", mip_enum)
                    unreal.EditorAssetLibrary.save_loaded_asset(tex)
                changed += 1
            except Exception as ex:
                errors.append({"name": str(a.asset_name), "error": str(ex)})
                log_warning(f"[texture_apply_preset] {a.asset_name}: {ex}")

        action = "Would apply" if dry_run else "Applied"
        log_info(f"[texture_apply_preset] {action} preset '{preset}' to {changed} textures")
        return {
            "status": "ok",
            "dry_run": dry_run,
            "preset": preset,
            "settings": {"compression": compression_str, "group": group_str, "srgb": srgb_val, "mip_gen": mip_str},
            "changed": changed,
            "errors": errors,
        }
    except Exception as e:
        log_error(f"[texture_apply_preset] {e}")
        return {"status": "error", "message": str(e)}

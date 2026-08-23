"""
UEFN TOOLBELT — Text Voxelizer
========================================
Render raw text strings into Texture2D masks, or voxelize them into 3D using
dense grids of StaticMesh blocks.

FEATURES:
  • Uses a headless PowerShell script to hook native Windows GDI/System.Drawing
  • Converts output textures into dense coordinate arrays
  • Merges thousands of individual voxel blocks into a single high-performance StaticMesh asset
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import unreal

from ..core import log_error, log_info, log_warning, resolve_content_path, save_asset
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Internal Math & PS Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dir(d: str):
    if not unreal.EditorAssetLibrary.does_directory_exist(d):
        unreal.EditorAssetLibrary.make_directory(d)

def _find_unique_name(directory: str, base: str) -> str:
    _ensure_dir(directory)
    name = "".join(c if c.isalnum() else "_" for c in base).strip("_") or "TextAsset"
    i = 0
    while True:
        suffix = "" if i == 0 else f"_{i}"
        path = f"{directory}/{name}{suffix}"
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            return path
        i += 1

def _render_text_via_powershell(
    text: str, font_size: int, w: int, h: int, step: int
) -> tuple[str, list[tuple[int, int]]]:
    """Generates a PNG and a voxel array via hidden Powershell System.Drawing"""
    tmp_png = os.path.join(tempfile.gettempdir(), "uefntoolbelt_text_cache.png")
    tmp_pts = os.path.join(tempfile.gettempdir(), "uefntoolbelt_text_pts_cache.txt")

    ps_png = tmp_png.replace("\\", "\\\\")
    ps_pts = tmp_pts.replace("\\", "\\\\")
    safe_text = text.replace("`", "'")
    step_safe = max(1, step)

    script = f"""
Add-Type -AssemblyName System.Drawing
$b = New-Object System.Drawing.Bitmap({w}, {h}, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($b)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.Clear([System.Drawing.Color]::Transparent)
$f = New-Object System.Drawing.Font('Arial', {font_size}, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$br = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = [System.Drawing.StringAlignment]::Center
$fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
$r = New-Object System.Drawing.RectangleF(0,0,{w},{h})
$g.DrawString(@"
{safe_text}
"@, $f, $br, $r, $fmt)
$b.Save('{ps_png}', [System.Drawing.Imaging.ImageFormat]::Png)

$sw = New-Object System.IO.StreamWriter('{ps_pts}', $false)
for($y=0; $y -lt {h}; $y+={step_safe}) {{
  for($x=0; $x -lt {w}; $x+={step_safe}) {{
    $c = $b.GetPixel($x,$y)
    if($c.A -gt 16) {{
      $sw.WriteLine(\"$x,$y\")
    }}
  }}
}}
$sw.Close()
$g.Dispose()
$b.Dispose()
    """

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True
        )
        if proc.returncode != 0:
            log_error(f"GDI Render Error: {proc.stderr}")
            return "", []
    except Exception as e:
        log_error(f"Subprocess failed: {e}")
        return "", []

    pts = []
    if os.path.exists(tmp_pts):
        with open(tmp_pts) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    pts.append((int(parts[0]), int(parts[1])))

    return tmp_png if os.path.exists(tmp_png) else "", pts


def _merge_voxel_actors(actors: list, target_path: str) -> str:
    eal = unreal.EditorAssetLibrary
    ell = getattr(unreal, "EditorLevelLibrary", None)
    opts_cls = getattr(unreal, "EditorScriptingMergeStaticMeshActorsOptions", None)

    if not ell or not hasattr(ell, "merge_static_mesh_actors") or not opts_cls:
        log_error("Asset Merge API is unavailable in this Unreal iteration.")
        return ""

    try:
        opts = opts_cls()
        if hasattr(opts, "base_package_name"): opts.base_package_name = target_path
        if hasattr(opts, "destroy_source_actors"): opts.destroy_source_actors = True
        if hasattr(opts, "spawn_merged_actor"): opts.spawn_merged_actor = True

        ell.merge_static_mesh_actors(actors, opts)
    except Exception as e:
        log_error(f"Voxel block merge failed: {e}")
        return ""

    if eal.does_asset_exist(target_path):
        return target_path

    # Check object path syntax
    obj_path = f"{target_path}.{target_path.rsplit('/',1)[-1]}"
    if eal.does_asset_exist(obj_path):
        return obj_path

    return ""


# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="text_render_texture",
    category="Generative",
    description="Renders a text string natively into a transparent Texture2D asset.",
    tags=["text", "texture", "render", "gdi", "font"]
)
def run_text_render_texture(
    text: str,
    asset_dir: str = "",
    asset_name: str = "T_RenderedText",
    font_size: int = 120,
    width: int = 1024,
    height: int = 512,
    **kwargs
) -> dict:
    asset_dir = resolve_content_path(asset_dir, "Generated/Text")
    if not text.strip():
        return {"status": "error", "error": "Text is empty"}

    png_path, _ = _render_text_via_powershell(text, max(8, font_size), max(64, width), max(64, height), 16)
    if not png_path:
        return {"status": "error", "error": "GDI pipeline failed"}

    unique_path = _find_unique_name(asset_dir, asset_name)
    leaf = unique_path.split("/")[-1]

    task = unreal.AssetImportTask()
    task.filename = png_path
    task.destination_path = asset_dir
    task.destination_name = leaf
    task.automated = True
    task.save = True

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = task.get_editor_property("imported_object_paths")

    if imported:
        unreal.EditorAssetLibrary.sync_browser_to_objects(imported)
        log_info(f"Rendered Text Texture saved to {imported[0]}")
        return {"status": "success", "asset_path": imported[0]}

    return {"status": "error", "error": "Engine import failed"}


@register_tool(
    name="text_voxelize_3d",
    category="Generative",
    description="Voxelizes a text string into a 3D StaticMesh asset using thousands of procedural cubes.",
    tags=["text", "voxel", "3d", "procedural", "mesh"]
)
def run_text_voxelize_3d(
    text: str,
    asset_dir: str = "",
    asset_name: str = "SM_VoxelText",
    font_size: int = 120,
    pixel_step: int = 8,
    depth_blocks: int = 3,
    fallback_cube: str = "/Engine/BasicShapes/Cube.Cube",
    **kwargs
) -> dict:
    asset_dir = resolve_content_path(asset_dir, "Generated/Text")
    if not text.strip():
        return {"status": "error", "error": "Text is empty"}

    _, pts = _render_text_via_powershell(text, max(12, font_size), 1024, 512, max(2, pixel_step))
    if not pts:
        return {"status": "error", "error": "GDI masking failed. Null pixels returned."}

    cube_obj = unreal.load_asset(fallback_cube)
    if not cube_obj or not isinstance(cube_obj, unreal.StaticMesh):
        log_error(f"Fallback cube required to voxelize: {fallback_cube}")
        return {"status": "error", "error": "Missing fallback cube geometry"}

    unique_path = _find_unique_name(asset_dir, asset_name)
    ell = unreal.EditorLevelLibrary
    actors = []

    unit = 50.0  # Cube native size * scale
    half_w, half_h = 512.0, 256.0

    log_info(f"Voxelizing '{text}' mapped to {len(pts)} 2D coordinates across depth_blocks={depth_blocks}...")

    with unreal.ScopedEditorTransaction("Spawn Text Voxels"):
        for (x, y) in pts:
            px = (x - half_w) * (unit / float(max(1, pixel_step)))
            pz = (half_h - y) * (unit / float(max(1, pixel_step)))
            for d in range(depth_blocks):
                py = float(d) * unit
                a = ell.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(px, py, pz), unreal.Rotator(0, 0, 0))
                if a:
                    a.static_mesh_component.set_static_mesh(cube_obj)
                    a.set_actor_scale3d(unreal.Vector(0.5, 0.5, 0.5))
                    actors.append(a)

        if not actors:
            return {"status": "error", "error": "Failed to spawn actor grid."}

        merged_path = _merge_voxel_actors(actors, unique_path)
        if not merged_path:
            log_error("Mesh merge failed. Leaving independent actors in level.")
            return {"status": "error", "error": "Merge failed", "spawned_count": len(actors)}

    # Save the output geometry
    try:
        save_asset(merged_path)
        unreal.EditorAssetLibrary.sync_browser_to_objects([merged_path])
    except Exception as e:
        # The merge succeeded in memory but the asset was not written. Saying
        # nothing here meant the tool reported success for a mesh that would
        # not survive a restart.
        log_warning(
            f"Voxelized mesh was created but could not be saved to "
            f"{merged_path}: {e}. Save it manually before closing the editor."
        )

    log_info(f"Successfully Voxelized Text to Solid Mesh: {merged_path} (from {len(actors)} cubes)")
    return {"status": "success", "asset_path": merged_path, "cubes_used": len(actors)}

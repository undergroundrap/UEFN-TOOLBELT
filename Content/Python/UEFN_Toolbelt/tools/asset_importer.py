"""
UEFN TOOLBELT — Asset Importer
========================================
Advanced importing tool that expands Epic's standard import tasks to fetch
images directly from http/https URLs and the Windows Clipboard.

FEATURES:
  • HTTP/HTTPS Image fetcher directly into Content Browser
  • Clipboard Image extractor (uses Pillow or PowerShell fallback)
  • Seamless native `@register_tool` integration with dynamic naming
"""

from __future__ import annotations

import os
import re
import tempfile
import urllib.parse
import urllib.request
import unreal

from ..core import log_info, log_error, log_warning, get_config, detect_project_mount
from ..core.safety_gate import SafetyGate
from ..registry import register_tool

# ─────────────────────────────────────────────────────────────────────────────
#  Generics
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_asset_name(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if not name:
        return ""
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name

def _next_sequential_name(dest_dir: str, base: str = "T_ImportedImage") -> str:
    idx = 1
    eal = unreal.EditorAssetLibrary
    while True:
        name = f"{base}_{idx:02d}"
        if not eal.does_asset_exist(f"{dest_dir}/{name}"):
            return name
        idx += 1

def _import_file_task(file_path: str, dest_dir: str, asset_name: str) -> str:
    if not os.path.exists(file_path):
        return ""
        
    eal = unreal.EditorAssetLibrary
    if not eal.does_directory_exist(dest_dir):
        eal.make_directory(dest_dir)

    task = unreal.AssetImportTask()
    task.filename = file_path
    task.destination_path = dest_dir
    task.destination_name = asset_name
    task.automated = True
    task.replace_existing = False
    task.save = False  # skip source-control checkout dialog; we save manually below

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    # Resolve the imported asset path
    dest_asset = f"{dest_dir}/{asset_name}"
    imported = task.get_editor_property("imported_object_paths") or []
    asset_path = dest_asset if eal.does_asset_exist(dest_asset) else (imported[0] if imported else "")

    if not asset_path:
        return ""

    # Sync Content Browser selection -- no save attempt (UEFN source control blocks it)
    eal.sync_browser_to_objects([asset_path])
    return asset_path

def _extract_clipboard_png(temp_path: str) -> bool:
    """
    Extract the current clipboard image to a PNG file.
    Tries three methods in order:
      1. PySide6 (already loaded by the dashboard -- most reliable)
      2. Pillow ImageGrab
      3. PowerShell (Windows fallback, no extra deps)
    """
    # -- 1. PySide6 (preferred -- already in memory) --
    try:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        qimg = cb.image()
        if not qimg.isNull():
            qimg.save(temp_path, "PNG")
            if os.path.exists(temp_path):
                return True
    except Exception:
        pass

    # -- 2. Pillow ImageGrab --
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is not None and hasattr(img, "save"):
            img.save(temp_path, "PNG")
            if os.path.exists(temp_path):
                return True
    except Exception:
        pass

    # -- 3. PowerShell (no extra deps, Windows only) --
    try:
        import subprocess
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$img=[Windows.Forms.Clipboard]::GetImage(); "
            "if($img -ne $null){$img.Save('"
            + temp_path.replace("\\", "\\\\")
            + "', [System.Drawing.Imaging.ImageFormat]::Png)}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False, capture_output=True, text=True
        )
        if os.path.exists(temp_path):
            return True
    except Exception as e:
        log_warning(f"Clipboard extraction fallback failed: {e}")

    return False

# ─────────────────────────────────────────────────────────────────────────────
#  Registered Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="import_image_from_url",
    category="Pipeline",
    description="Downloads an image directly from a URL into the Editor Content Browser as a Texture2D.",
    tags=["import", "url", "image", "texture", "download"]
)
def run_import_image_from_url(
    url: str,
    asset_dir: str = "",
    asset_name: str = "",
    **kwargs
) -> dict:
    if not asset_dir:
        asset_dir = get_config().get("import.default_dir") or f"/{detect_project_mount()}/UEFN_Toolbelt/Textures"
    if not url.strip():
        log_error("Image URL is required.")
        return {"error": "Missing URL"}

    clean_name = _sanitize_asset_name(asset_name)
    if not clean_name:
        # Infer from URL
        try:
            leaf = os.path.basename(urllib.parse.urlparse(url).path)
            clean_name = _sanitize_asset_name(leaf.rsplit(".", 1)[0] if "." in leaf else leaf)
        except Exception:
            pass
            
    if not clean_name:
        clean_name = _next_sequential_name(asset_dir)
        
    _, ext = os.path.splitext(urllib.parse.urlparse(url).path)
    ext = (ext or ".png").lower()
    if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".exr", ".hdr", ".webp"):
        ext = ".png"
        
    # Phase 14: Safety Gate Validation
    SafetyGate.enforce_safety(asset_dir)
    
    tmp_path = os.path.join(tempfile.gettempdir(), f"uefn_fetch_{clean_name}{ext}")
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "UEFN Toolbelt/1.0.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        with open(tmp_path, "wb") as f:
            f.write(data)
    except Exception as e:
        log_error(f"Failed to fetch image from URL: {e}")
        return {"error": str(e)}

    result_path = _import_file_task(tmp_path, asset_dir, clean_name)
    if not result_path:
        log_error("Unreal Engine failed to import the downloaded file.")
        return {"error": "Engine import failed"}

    log_info(f"Successfully downloaded and imported Texture to: {result_path}")
    return {"status": "success", "asset_path": result_path}


@register_tool(
    name="import_image_from_clipboard",
    category="Pipeline",
    description="Captures the current image sitting on the Windows Clipboard and imports it as a Texture2D.",
    tags=["import", "clipboard", "image", "texture", "paste"]
)
def run_import_image_from_clipboard(
    asset_dir: str = "",
    asset_name: str = "",
    **kwargs
) -> dict:
    if not asset_dir:
        asset_dir = get_config().get("import.default_dir") or f"/{detect_project_mount()}/UEFN_Toolbelt/Textures"
    clean_name = _sanitize_asset_name(asset_name) or _next_sequential_name(asset_dir)
    # Phase 14: Safety Gate Validation
    SafetyGate.enforce_safety(asset_dir)
    
    tmp_path = os.path.join(tempfile.gettempdir(), f"uefn_clip_{clean_name}.png")
    
    if not _extract_clipboard_png(tmp_path):
        log_error("No valid image found on the Windows clipboard, or extraction failed.")
        return {"error": "Clipboard extraction failed"}
        
    result_path = _import_file_task(tmp_path, asset_dir, clean_name)
    if not result_path:
        log_error("Engine failed to import clipboard PNG.")
        return {"error": "Engine import failed"}

    log_info(f"Successfully imported clipboard image to: {result_path}")
    return {"status": "success", "asset_path": result_path}


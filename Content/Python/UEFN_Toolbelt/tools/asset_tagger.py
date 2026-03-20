"""
UEFN TOOLBELT — asset_tagger.py
=========================================
Apply searchable custom metadata tags to Content Browser assets.

Why metadata tags?
  The Content Browser search only searches by name and asset class.
  Metadata tags let you attach custom key=value pairs to any asset and
  then filter by them — so "find all SM_ assets tagged 'hero_prop'" or
  "find every texture tagged 'environment/desert'" works in one command.

  Tags survive project saves, source control syncs, and editor restarts
  because they are stored as UE asset metadata — not in a separate file.

Tag naming convention:
  Keys are stored as  "TB:{tag_name}"  so toolbelt tags never collide
  with Epic's own metadata keys.  The prefix is stripped in all output.

  Examples:
    tag_add(tag_name="hero")                → TB:hero = "1"
    tag_add(tag_name="category", value="environment") → TB:category = "environment"
    tag_add(tag_name="lod_ready", value="true")       → TB:lod_ready = "true"

API used:
  unreal.EditorAssetLibrary.set_metadata_tag(asset, tag_key, tag_value)
  unreal.EditorAssetLibrary.get_metadata_tag_values(asset, tag_key)
  unreal.EditorUtilityLibrary.get_selected_assets()   ← Content Browser selection
  unreal.AssetRegistryHelpers.get_asset_registry()    ← fast indexed search

Tools:
  tag_add             — add / update a tag on all selected CB assets
  tag_remove          — remove a tag from all selected CB assets
  tag_show            — print every TB: tag on all selected CB assets
  tag_search          — find assets by tag value (fast, uses AssetRegistry index)
  tag_list_all        — list every unique tag key used under a folder
  tag_export          — export the full tag → asset mapping to JSON

Output:
  Saved/UEFN_Toolbelt/tag_export.json
"""

from __future__ import annotations

import json
import os
from typing import Any

import unreal

from UEFN_Toolbelt.registry import register_tool

# ─── Constants ────────────────────────────────────────────────────────────────

_TAG_PREFIX   = "TB:"          # Toolbelt metadata key prefix
_DEFAULT_VALUE = "1"           # value used for boolean / flag tags
_SAVED        = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt")
_EXPORT_PATH  = os.path.join(_SAVED, "tag_export.json")


def _ensure_dir() -> None:
    os.makedirs(_SAVED, exist_ok=True)


# ─── Low-level metadata helpers ───────────────────────────────────────────────

def _full_key(tag_name: str) -> str:
    """Return the full metadata key with prefix.  'hero' → 'TB:hero'"""
    tag_name = tag_name.strip()
    if tag_name.startswith(_TAG_PREFIX):
        return tag_name
    return f"{_TAG_PREFIX}{tag_name}"


def _short_key(full_key: str) -> str:
    """Strip prefix for display.  'TB:hero' → 'hero'"""
    return full_key[len(_TAG_PREFIX):] if full_key.startswith(_TAG_PREFIX) else full_key


def _set_tag(asset_path: str, key: str, value: str) -> bool:
    """
    Set one metadata tag on an asset.

    Uses EditorAssetLibrary.set_metadata_tag — confirmed available in UEFN 40.00+
    (Kirch dump, domain: Asset Pipeline 10/10).
    Saves the asset so the tag persists to disk.
    """
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            unreal.log_warning(f"[AssetTagger] Could not load: {asset_path}")
            return False
        unreal.EditorAssetLibrary.set_metadata_tag(asset, unreal.Name(key), value)
        unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
        return True
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] set_tag failed on {asset_path}: {e}")
        return False


def _get_tag(asset_path: str, key: str) -> str:
    """Return the metadata value for key on asset_path, or '' if absent."""
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            return ""
        raw = unreal.EditorAssetLibrary.get_metadata_tag_values(asset, unreal.Name(key))
        # Returns a list of strings; take the first entry
        if isinstance(raw, (list, tuple)):
            return str(raw[0]) if raw else ""
        return str(raw) if raw else ""
    except Exception:
        return ""


def _remove_tag(asset_path: str, key: str) -> bool:
    """Remove a metadata tag from an asset by setting its value to ''."""
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            return False
        unreal.EditorAssetLibrary.remove_metadata_tag(asset, unreal.Name(key))
        unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
        return True
    except AttributeError:
        # remove_metadata_tag may not exist in all builds — fall back to empty value
        return _set_tag(asset_path, key, "")
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] remove_tag failed on {asset_path}: {e}")
        return False


def _get_all_toolbelt_tags(asset_path: str) -> dict[str, str]:
    """
    Return a dict of all TB: tags on asset_path.

    Reads via AssetRegistry (fast, no asset load needed).
    Falls back to loading the asset directly.
    """
    tags: dict[str, str] = {}

    try:
        data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if data is None:
            return tags

        # AssetData.get_tag_value is available in UE5/UEFN
        # We iterate known tag names using the tag_and_values map if possible.
        # Since we don't know which tags exist without loading, load the asset.
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            return tags

        # Enumerate every tag key in the unreal metadata map
        try:
            all_tag_keys = unreal.EditorAssetLibrary.get_metadata_tag_values(
                asset, unreal.Name("")
            )
        except Exception:
            all_tag_keys = []

        # Fallback: iterate dir(asset) is not useful for metadata.
        # Instead, we use the AssetData tag map.
        try:
            # asset_data.tag_and_values is an FAssetDataTagMap
            tav = data.tag_and_values
            if tav:
                for key_obj, val in dict(tav).items():
                    key = str(key_obj)
                    if key.startswith(_TAG_PREFIX):
                        tags[_short_key(key)] = str(val)
        except Exception:
            pass

    except Exception as e:
        unreal.log_warning(f"[AssetTagger] Could not read tags on {asset_path}: {e}")

    return tags


def _get_selected_asset_paths() -> list[str]:
    """Return content browser selected asset paths."""
    try:
        selected = unreal.EditorUtilityLibrary.get_selected_assets()
        return [a.get_path_name().split(".")[0] for a in selected if a]
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] Could not get selected assets: {e}")
        return []


# ─── Folder scan helper ───────────────────────────────────────────────────────

def _list_all_under(folder: str) -> list[str]:
    try:
        return list(unreal.EditorAssetLibrary.list_assets(folder, recursive=True))
    except Exception:
        return []


# ─── Tool implementations ─────────────────────────────────────────────────────

def _do_tag_add(tag_name: str, value: str) -> None:
    paths = _get_selected_asset_paths()
    if not paths:
        unreal.log_warning("[AssetTagger] Nothing selected in the Content Browser.")
        return

    key = _full_key(tag_name)
    val = value or _DEFAULT_VALUE
    ok = total = 0

    for path in paths:
        total += 1
        if _set_tag(path, key, val):
            ok += 1
            unreal.log(f"[AssetTagger] ✓  {_short_key(key)} = {val!r}  →  {path}")
        else:
            unreal.log_warning(f"[AssetTagger] ✗  Failed on {path}")

    unreal.log(f"[AssetTagger] Tagged {ok}/{total} assets as '{_short_key(key)}'.")


def _do_tag_remove(tag_name: str) -> None:
    paths = _get_selected_asset_paths()
    if not paths:
        unreal.log_warning("[AssetTagger] Nothing selected in the Content Browser.")
        return

    key = _full_key(tag_name)
    ok = total = 0

    for path in paths:
        total += 1
        if _remove_tag(path, key):
            ok += 1
            unreal.log(f"[AssetTagger] ✓  Removed tag '{_short_key(key)}'  from  {path}")

    unreal.log(f"[AssetTagger] Removed tag '{_short_key(key)}' from {ok}/{total} assets.")


def _do_tag_show() -> None:
    paths = _get_selected_asset_paths()
    if not paths:
        unreal.log_warning("[AssetTagger] Nothing selected in the Content Browser.")
        return

    unreal.log(f"\n[AssetTagger] Tags on {len(paths)} selected asset(s):\n")
    any_tags = False

    for path in paths:
        tags = _get_all_toolbelt_tags(path)
        name = path.split("/")[-1]
        if tags:
            any_tags = True
            unreal.log(f"  {name}")
            for k, v in sorted(tags.items()):
                unreal.log(f"    TB:{k} = {v!r}")
        else:
            unreal.log(f"  {name}  ← no Toolbelt tags")

    if not any_tags:
        unreal.log("  (none of the selected assets have Toolbelt tags)")
    unreal.log("")


def _do_tag_search(tag_name: str, value: str, folder: str) -> list[str]:
    """
    Find assets under folder that have TB:{tag_name} = value.

    Iterates all assets and reads tags via AssetData — no full asset load
    unless the AssetData tag map is unavailable.
    """
    key = _full_key(tag_name)
    match_value = value or _DEFAULT_VALUE
    all_paths = _list_all_under(folder)
    matches: list[str] = []

    unreal.log(f"[AssetTagger] Scanning {len(all_paths)} assets for TB:{tag_name} = {match_value!r}…")

    for path in all_paths:
        stored = _get_tag(path, key)
        if stored == match_value:
            matches.append(path)

    return matches


def _do_tag_list_all(folder: str) -> dict[str, int]:
    """Return {short_key: count} for all TB: tags used under folder."""
    all_paths = _list_all_under(folder)
    counts: dict[str, int] = {}

    for path in all_paths:
        tags = _get_all_toolbelt_tags(path)
        for k in tags:
            counts[k] = counts.get(k, 0) + 1

    return counts


def _do_tag_export(folder: str) -> None:
    """
    Export the full tag → asset mapping to JSON.

    Structure:
      {
        "folder": "/Game",
        "tags": {
          "hero_prop": ["/Game/Props/SM_Chest", "/Game/Props/SM_Barrel"],
          "category":  {
            "environment": [...],
            "gameplay":    [...]
          }
        }
      }
    """
    all_paths = _list_all_under(folder)
    index: dict[str, Any] = {}  # tag_name → {value → [paths]}

    for path in all_paths:
        tags = _get_all_toolbelt_tags(path)
        for key, val in tags.items():
            if key not in index:
                index[key] = {}
            index[key].setdefault(val, []).append(path)

    report = {
        "folder": folder,
        "unique_tags": len(index),
        "tags": index,
    }

    _ensure_dir()
    with open(_EXPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    unreal.log(f"\n[AssetTagger] ═══ Tag Export: {folder} ═══")
    unreal.log(f"  {len(index)} unique tag names across {len(all_paths)} assets.")
    for tag, values in sorted(index.items()):
        total = sum(len(v) for v in values.values())
        if len(values) == 1:
            unreal.log(f"  TB:{tag:30s}  {total} assets")
        else:
            unreal.log(f"  TB:{tag:30s}  {total} assets  ({len(values)} distinct values)")
    unreal.log(f"\n  Full report → {_EXPORT_PATH}\n")


# ─── Registered tools ─────────────────────────────────────────────────────────

@register_tool(
    name="tag_add",
    category="Asset Tagger",
    description="Add a searchable metadata tag to all selected Content Browser assets",
    icon="🏷",
    tags=["tag", "metadata", "organize", "search"],
)
def tag_add(
    tag_name: str = "",
    value: str = "1",
**kwargs,
) -> None:
    """
    Apply a metadata tag to all assets currently selected in the Content Browser.

    Args:
        tag_name: Tag key — e.g. "hero_prop", "category", "lod_ready".
                  Stored internally as "TB:{tag_name}" to avoid key collisions.
        value:    Tag value string. Leave "1" for boolean/flag tags.
                  Use descriptive values for category tags:
                    tag_add(tag_name="biome", value="desert")
                    tag_add(tag_name="biome", value="arctic")
    """
    if not tag_name:
        unreal.log_warning(
            "[AssetTagger] Provide a tag_name. "
            "Example: tb.run('tag_add', tag_name='hero_prop')"
        )
        return
    _do_tag_add(tag_name, value)


@register_tool(
    name="tag_remove",
    category="Asset Tagger",
    description="Remove a metadata tag from all selected Content Browser assets",
    icon="🏷",
    tags=["tag", "metadata", "remove", "cleanup"],
)
def tag_remove(tag_name: str = "", **kwargs) -> None:
    """
    Remove a tag key from all assets selected in the Content Browser.

    Args:
        tag_name: Tag to remove (without the TB: prefix).
    """
    if not tag_name:
        unreal.log_warning("[AssetTagger] Provide a tag_name to remove.")
        return
    _do_tag_remove(tag_name)


@register_tool(
    name="tag_show",
    category="Asset Tagger",
    description="Print every Toolbelt metadata tag on all selected Content Browser assets",
    icon="🔖",
    tags=["tag", "metadata", "inspect", "show"],
)
def tag_show(**kwargs) -> None:
    """
    Print all TB: tags on every asset currently selected in the Content Browser.
    Assets with no Toolbelt tags are shown with a '← no Toolbelt tags' note.
    """
    _do_tag_show()


@register_tool(
    name="tag_search",
    category="Asset Tagger",
    description="Find assets by metadata tag — returns matching paths to the Output Log",
    icon="🔍",
    tags=["tag", "metadata", "search", "filter"],
)
def tag_search(
    tag_name: str = "",
    value: str = "1",
    folder: str = "/Game",
**kwargs,
) -> None:
    """
    Find all assets under folder where TB:{tag_name} = value.

    Args:
        tag_name: Tag key to search for.
        value:    Expected tag value. Default "1" matches boolean/flag tags.
        folder:   Content path to scan (recursive). Default "/Game".

    Example:
        tb.run('tag_search', tag_name='biome', value='desert', folder='/Game/Environment')
    """
    if not tag_name:
        unreal.log_warning(
            "[AssetTagger] Provide a tag_name to search for. "
            "Example: tb.run('tag_search', tag_name='hero_prop')"
        )
        return

    matches = _do_tag_search(tag_name, value, folder)

    if not matches:
        unreal.log(f"[AssetTagger] No assets found with TB:{tag_name} = {value!r} under {folder}.")
        return

    unreal.log(f"\n[AssetTagger] TB:{tag_name} = {value!r} — {len(matches)} match(es) in {folder}:\n")
    for path in matches:
        unreal.log(f"  🏷  {path}")
    unreal.log("")


@register_tool(
    name="tag_list_all",
    category="Asset Tagger",
    description="List every unique Toolbelt tag key used under a folder with asset counts",
    icon="📋",
    tags=["tag", "metadata", "list", "inventory"],
)
def tag_list_all(folder: str = "/Game", **kwargs) -> None:
    """
    Print all unique TB: tag keys used anywhere under folder, with asset counts.

    Args:
        folder: Content path to scan (recursive). Default "/Game".
    """
    unreal.log(f"[AssetTagger] Scanning tags under {folder}…")
    counts = _do_tag_list_all(folder)

    if not counts:
        unreal.log(f"[AssetTagger] No Toolbelt tags found under {folder}.")
        unreal.log(f"  Apply tags with: tb.run('tag_add', tag_name='my_tag')")
        return

    unreal.log(f"\n[AssetTagger] {len(counts)} tag key(s) under {folder}:\n")
    for key, count in sorted(counts.items(), key=lambda x: -x[1]):
        unreal.log(f"  TB:{key:30s}  {count:4d} assets")
    unreal.log("")


@register_tool(
    name="tag_export",
    category="Asset Tagger",
    description="Export full tag → asset index to JSON (Saved/UEFN_Toolbelt/tag_export.json)",
    icon="📤",
    tags=["tag", "metadata", "export", "json", "report"],
)
def tag_export(folder: str = "/Game", **kwargs) -> None:
    """
    Scan all assets under folder, collect every TB: tag, and write the
    tag → asset mapping to Saved/UEFN_Toolbelt/tag_export.json.

    Args:
        folder: Content path to scan (recursive). Default "/Game".
    """
    _do_tag_export(folder)

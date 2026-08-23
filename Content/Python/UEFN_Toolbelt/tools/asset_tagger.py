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
  unreal.EditorAssetLibrary.get_metadata_tag(asset, tag_key)          -> str
  unreal.EditorAssetLibrary.get_metadata_tag_values(asset)            -> map
      NOTE: the plural form takes NO key. Passing one raises, and this file
      did exactly that for every read, so the whole search side never worked.
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

from UEFN_Toolbelt.core import resolve_scan_path, scannable_assets
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


def _tag_result(done: int, attempted: int, tag_name: str,
                verb: str, **extra) -> dict:
    """Report what persisted, not what was attempted.

    tag_add and tag_remove both returned {"status": "ok"} no matter what
    happened, while the worker counted successes and threw them away.
    """
    out = {"tag": tag_name, verb: done, "attempted": attempted, **extra}
    if attempted == 0:
        out["status"] = "error"
        out["reason"] = "nothing_selected"
        return out
    if done == 0:
        out["status"] = "error"
        out["reason"] = "nothing_persisted"
        return out
    out["status"] = "ok" if done == attempted else "partial"
    return out


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
        # save_asset returns False rather than raising when the package cannot be
        # written - read-only engine content, or checked out by someone else.
        # Discarding it meant the tag was set in memory, never persisted, and
        # reported as a success. tag_search would then find nothing, so the two
        # tools disagreed and both passed. Observed live on 2026-08-22 tagging
        # /Engine/BasicShapes/Cube.
        if not unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False):
            unreal.log_warning(
                f"[AssetTagger] {asset_path}: tag set in memory but the asset "
                f"could not be saved, so it will not persist. Engine and "
                f"read-only content cannot be tagged."
            )
            return False
        return True
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] set_tag failed on {asset_path}: {e}")
        return False


def _load_for_tags(asset_path: str):
    """Load an asset for tag reading, or None if it cannot be loaded."""
    try:
        return unreal.EditorAssetLibrary.load_asset(asset_path)
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] Could not load {asset_path}: {e}")
        return None


def _metadata_map(asset) -> dict | None:
    """Every metadata tag on an asset as {key: value}, or None if unreadable.

    get_metadata_tag_values takes only the object. Note this is package
    UMetaData, which is NOT the same thing as AssetData.tag_and_values - that
    is the asset-registry tag map and never contains tags written with
    set_metadata_tag, which is why reading it always returned nothing.
    """
    try:
        raw = unreal.EditorAssetLibrary.get_metadata_tag_values(asset)
    except Exception as e:
        unreal.log_warning(f"[AssetTagger] metadata unreadable: {e}")
        return None
    if raw is None:
        return {}
    try:
        return {str(k): str(v) for k, v in dict(raw).items()}
    except Exception:
        try:
            return {str(k): str(raw[k]) for k in raw}
        except Exception as e:
            unreal.log_warning(f"[AssetTagger] metadata map unreadable: {e}")
            return None


def _get_tag(asset_path: str, key: str) -> str | None:
    """
    Metadata value for key on asset_path.

    '' when the asset genuinely has no such tag, None when it could not be read.
    Callers must not conflate the two: an unreadable asset may well carry the tag.
    """
    asset = _load_for_tags(asset_path)
    if asset is None:
        return None

    # EditorAssetLibrary exposes two readers and they are NOT interchangeable:
    #
    #   get_metadata_tag(object, tag)   -> str              one tag
    #   get_metadata_tag_values(object) -> Map(Name, str)   ALL tags, no key arg
    #
    # This used to call the PLURAL form with a key. That is a one-argument
    # function, so every call raised TypeError, the except swallowed it, and the
    # function returned None - "could not be read" - for every asset ever
    # checked. tag_search, tag_list_all and tag_export therefore always found
    # nothing, no matter what had been written. Confirmed live 2026-08-22: a tag
    # that had just been written and saved to disk came back unreadable.
    single = getattr(unreal.EditorAssetLibrary, "get_metadata_tag", None)
    if single is not None:
        try:
            return str(single(asset, unreal.Name(key)) or "")
        except Exception:
            pass

    values = _metadata_map(asset)
    if values is None:
        return None
    return str(values.get(key, ""))


def _remove_tag(asset_path: str, key: str) -> bool:
    """Remove a metadata tag from an asset by setting its value to ''."""
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            return False
        unreal.EditorAssetLibrary.remove_metadata_tag(asset, unreal.Name(key))
        if not unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False):
            unreal.log_warning(
                f"[AssetTagger] {asset_path}: tag removed in memory but the asset "
                f"could not be saved, so the removal will not persist."
            )
            return False
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

        # The real source of truth: package metadata, which is where
        # set_metadata_tag writes. The old code called this with a key (it takes
        # none), discarded the result, and then read AssetData.tag_and_values
        # instead - the asset-registry map, which never carries these tags. That
        # is why tag_list_all and tag_export always reported zero.
        values = _metadata_map(asset)
        if values:
            for key, val in values.items():
                if key.startswith(_TAG_PREFIX):
                    tags[_short_key(key)] = str(val)

        # AssetData tags are a secondary source: some tags are surfaced through
        # the registry as well, and reading both costs nothing.
        try:
            tav = data.tag_and_values
            if tav:
                for key_obj, val in dict(tav).items():
                    key = str(key_obj)
                    if key.startswith(_TAG_PREFIX):
                        tags.setdefault(_short_key(key), str(val))
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
        return scannable_assets(
            unreal.EditorAssetLibrary.list_assets(folder, recursive=True)
        )
    except Exception as e:
        # An empty list here is indistinguishable from an empty folder, and every
        # caller reports "no tags found" either way. Say so instead.
        unreal.log_warning(f"[AssetTagger] could not list {folder}: {e}")
        return []


# ─── Tool implementations ─────────────────────────────────────────────────────

def _do_tag_add(tag_name: str, value: str,
                manual_paths: list[str] = None) -> tuple[int, int]:
    """(tagged, attempted). Both counts were computed and then discarded."""
    paths = manual_paths if manual_paths is not None else _get_selected_asset_paths()
    if not paths:
        unreal.log_warning("[AssetTagger] Nothing selected and no paths provided.")
        return 0, 0

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
    return ok, total


def _do_tag_remove(tag_name: str,
                   manual_paths: list[str] = None) -> tuple[int, int]:
    """(removed, attempted)."""
    paths = manual_paths if manual_paths is not None else _get_selected_asset_paths()
    if not paths:
        unreal.log_warning("[AssetTagger] Nothing selected and no paths provided.")
        return 0, 0

    key = _full_key(tag_name)
    ok = total = 0

    for path in paths:
        total += 1
        if _remove_tag(path, key):
            ok += 1
            unreal.log(f"[AssetTagger] ✓  Removed tag '{_short_key(key)}'  from  {path}")

    unreal.log(f"[AssetTagger] Removed tag '{_short_key(key)}' from {ok}/{total} assets.")
    return ok, total


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

    unreadable = 0
    for path in all_paths:
        stored = _get_tag(path, key)
        if stored is None:
            unreadable += 1
            continue
        if stored == match_value:
            matches.append(path)

    if unreadable:
        unreal.log_warning(
            f"[AssetTagger] {unreadable} asset(s) could not be read — these "
            f"results are incomplete, not empty. Any of them may carry the tag."
        )
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


def _do_tag_export(folder: str) -> int:
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
    return len(index)


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
    asset_paths: list[str] = None,
    **kwargs,
) -> dict:
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
        return {"status": "error", "message": "tag_name is required."}
    tagged, attempted = _do_tag_add(tag_name, value, manual_paths=asset_paths)
    return _tag_result(tagged, attempted, tag_name, "tagged", value=value)


@register_tool(
    name="tag_remove",
    category="Asset Tagger",
    description="Remove a metadata tag from all selected Content Browser assets",
    icon="🏷",
    tags=["tag", "metadata", "remove", "cleanup"],
)
def tag_remove(tag_name: str = "", asset_paths: list[str] = None, **kwargs) -> dict:
    """
    Remove a tag key from all assets selected in the Content Browser.

    Args:
        tag_name: Tag to remove (without the TB: prefix).
    """
    if not tag_name:
        unreal.log_warning("[AssetTagger] Provide a tag_name to remove.")
        return {"status": "error", "message": "tag_name is required."}
    removed, attempted = _do_tag_remove(tag_name, manual_paths=asset_paths)
    return _tag_result(removed, attempted, tag_name, "removed")


@register_tool(
    name="tag_show",
    category="Asset Tagger",
    description="Print every Toolbelt metadata tag on all selected Content Browser assets",
    icon="🔖",
    tags=["tag", "metadata", "inspect", "show"],
)
def tag_show(**kwargs) -> dict:
    """
    Print all TB: tags on every asset currently selected in the Content Browser.
    Assets with no Toolbelt tags are shown with a '← no Toolbelt tags' note.
    """
    _do_tag_show()
    return {"status": "ok"}


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
    folder: str = "",
**kwargs,
) -> dict:
    """
    Find all assets under folder where TB:{tag_name} = value.

    Args:
        tag_name: Tag key to search for.
        value:    Expected tag value. Default "1" matches boolean/flag tags.
        folder:   Content path to scan (recursive). Blank resolves to your
                  project mount - never /Game, which in UEFN is Epic's install.

    Returns:
        dict: {"status", "count", "matches": [asset_path]}

    Example:
        tb.run('tag_search', tag_name='biome', value='desert', folder='/Game/Environment')
    """
    folder = resolve_scan_path(folder)
    if not tag_name:
        unreal.log_warning(
            "[AssetTagger] Provide a tag_name to search for. "
            "Example: tb.run('tag_search', tag_name='hero_prop')"
        )
        return {"status": "error", "message": "tag_name is required."}

    matches = _do_tag_search(tag_name, value, folder)

    if not matches:
        unreal.log(f"[AssetTagger] No assets found with TB:{tag_name} = {value!r} under {folder}.")
        return {"status": "ok", "count": 0, "matches": []}

    unreal.log(f"\n[AssetTagger] TB:{tag_name} = {value!r} — {len(matches)} match(es) in {folder}:\n")
    for path in matches:
        unreal.log(f"  🏷  {path}")
    unreal.log("")
    return {"status": "ok", "count": len(matches), "matches": matches}


@register_tool(
    name="tag_list_all",
    category="Asset Tagger",
    description="List every unique Toolbelt tag key used under a folder with asset counts",
    icon="📋",
    tags=["tag", "metadata", "list", "inventory"],
)
def tag_list_all(folder: str = "", **kwargs) -> dict:
    """
    Print all unique TB: tag keys used anywhere under folder, with asset counts.

    Args:
        folder: Content path to scan (recursive). Default "/Game".

    Returns:
        dict: {"status", "count", "tags": {key: asset_count}}
    """
    folder = resolve_scan_path(folder)
    unreal.log(f"[AssetTagger] Scanning tags under {folder}…")
    counts = _do_tag_list_all(folder)

    if not counts:
        unreal.log(f"[AssetTagger] No Toolbelt tags found under {folder}.")
        unreal.log("  Apply tags with: tb.run('tag_add', tag_name='my_tag')")
        return {"status": "ok", "count": 0, "tags": {}}

    unreal.log(f"\n[AssetTagger] {len(counts)} tag key(s) under {folder}:\n")
    for key, count in sorted(counts.items(), key=lambda x: -x[1]):
        unreal.log(f"  TB:{key:30s}  {count:4d} assets")
    unreal.log("")
    return {"status": "ok", "count": len(counts), "tags": counts}


@register_tool(
    name="tag_export",
    category="Asset Tagger",
    description="Export full tag → asset index to JSON (Saved/UEFN_Toolbelt/tag_export.json)",
    icon="📤",
    tags=["tag", "metadata", "export", "json", "report"],
)
def tag_export(folder: str = "", **kwargs) -> dict:
    """
    Scan all assets under folder, collect every TB: tag, and write the
    tag → asset mapping to Saved/UEFN_Toolbelt/tag_export.json.

    Args:
        folder: Content path to scan (recursive). Default "/Game".

    Returns:
        dict: {"status", "path", "unique_tags": int}
    """
    folder = resolve_scan_path(folder)
    unique_tags = _do_tag_export(folder)
    return {"status": "ok", "path": _EXPORT_PATH, "unique_tags": unique_tags}

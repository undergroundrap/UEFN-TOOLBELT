"""
UEFN TOOLBELT — Core Utilities
========================================
Shared helpers used by every tool module.
"""

from __future__ import annotations

import contextlib
import math
import os
import random
from collections.abc import Generator, Iterable
from typing import Optional

import unreal

from .config import DEFAULTS, Config, get_config  # noqa: F401 — re-exported for tools
from .theme import PALETTE, QSS  # noqa: F401 — re-exported for tools
from .theme import color as theme_color

# ─────────────────────────────────────────────────────────────────────────────
#  Project Path Utilities
#  Always use these — never call Paths.project_content_dir() or guess a mount.
#  See docs/UEFN_QUIRKS.md Quirk #23 for the full explanation.
# ─────────────────────────────────────────────────────────────────────────────

# Engine, known Epic plugin mounts, and Fortnite game pak mounts that are
# never the user's project.  Add entries here as new paks are discovered.
PLUGIN_MOUNTS: frozenset = frozenset({
    # Core engine
    "Engine", "Script", "Epic",
    # Fortnite game paks — these dwarf any user project in AR entry count
    "Game", "FortniteGame", "Fortnite", "BRCosmetics", "BRSharedContent",
    "BRShooting", "BRLimitedTime", "BRItems", "Fort", "FortItemContents",
    "Athena", "AthenaContent", "FortCosmetics", "FortCreative",
    "CampFire", "CampFireCore",
    # Epic plugin mounts
    "Paper2D", "QualityAssistEd", "Niagara", "EnhancedInput",
    "ModelingEditorAssets", "ControlRig",
    "ACLPlugin", "AnimationLocomotionLibrary", "AnimationWarping", "CommonUI",
    "GameplayAbilities", "GameplayTasks", "GameplayMessageRouter", "StructUtils",
    "Chooser", "UIExtension", "ModularGameplay", "ModularGameplayActors",
    "DataRegistry", "SmartObjects", "StateTreeEditorModule", "GameFeatures",
    "ReplicationGraph", "PhysicsControl",
})


def detect_project_mount() -> str:
    """
    Return the user's project Content Browser mount point.

    Primary strategy: walk up from __file__ to find the folder that contains
    the 'Content' directory — that folder's name IS the project mount.  This
    is the only 100% reliable method; AR-count heuristics fail when Fortnite
    game paks (BRCosmetics, etc.) are loaded, as they have far more entries.

    Fallback: AR path count excluding PLUGIN_MOUNTS (catches edge cases where
    __file__ walkup is unavailable or returns an unexpected path).

    Returns e.g. "Device_API_Mapping" (no leading slash).
    """
    # ── Primary: __file__ walkup ──────────────────────────────────────────
    try:
        path = os.path.abspath(__file__).replace("\\", "/")
        parts = path.split("/")
        for i, part in enumerate(parts):
            if part == "Content" and i > 0:
                candidate = parts[i - 1]
                if candidate and candidate not in PLUGIN_MOUNTS:
                    return candidate
    except Exception:
        pass

    # ── Fallback: AR entry count (skips all known game/plugin mounts) ─────
    try:
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        counts: dict = {}
        for p in ar.get_all_cached_paths():
            root = p.strip("/").split("/")[0]
            if root and root not in PLUGIN_MOUNTS:
                counts[root] = counts.get(root, 0) + 1
        if counts:
            return max(counts, key=lambda k: counts[k])
    except Exception:
        pass
    return "Game"


# ─────────────────────────────────────────────────────────────────────────────
#  Engine API availability
#  UEFN force-updates with the live Fortnite build, so an API a tool depends on
#  can vanish between sessions with no warning. Tools that touch a removable API
#  should preflight it here and refuse with a specific reason, rather than
#  surfacing a raw AttributeError from somewhere deep inside a loop.
#  smoke_test Layer 2 reports the same removals up front.
# ─────────────────────────────────────────────────────────────────────────────

def missing_unreal_apis(*names: str) -> list[str]:
    """
    Return the subset of `names` this engine build does not expose.

    Accepts "ClassName" or "ClassName.method_name".

        missing_unreal_apis("EditorBlueprintLibrary", "Vector.up")
    """
    missing: list[str] = []
    for name in names:
        head, _, attr = name.partition(".")
        obj = getattr(unreal, head, None)
        if obj is None or (attr and not hasattr(obj, attr)):
            missing.append(name)
    return missing


def api_unavailable(tool: str, missing: list[str],
                    removed_in: str = "UEFN 42.00 (UE 6.0)") -> dict:
    """
    Standard refusal payload for a tool whose engine API is gone.

    Returns the same {"status": "error", ...} shape every other tool uses, so
    callers and MCP clients can handle it without special-casing.
    """
    msg = (
        f"{tool} is unavailable in this engine build: {', '.join(missing)} "
        f"not exposed (removed in {removed_in}). The tool is disabled rather "
        f"than failing part-way through. Run tb.smoke_test() for the full list."
    )
    log_warning(msg)
    return {
        "status": "error",
        "reason": "engine_api_unavailable",
        "missing_apis": missing,
        "message": msg,
    }


def is_scannable_asset(path: str) -> bool:
    """
    False for object paths that are not standalone assets.

    ':' marks a sub-object inside a package — e.g.
    /P/MyLevel.MyLevel:PersistentLevel.ActorFolder_UID_xxx. Under one-file-per-actor
    a level yields thousands of these; they all resolve to the same owning package
    and none can be loaded, renamed or moved individually.

    '$' appears in UEFN 42.00 Verse digest paths ($Digest, $DebugData,
    my_device$OnBegin). EditorAssetSubsystem rejects them outright — "Can't
    convert the path $Digest because it contains invalid characters" — logging an
    editor error on every lookup.

    EditorAssetLibrary.list_assets() returns both kinds, so anything that
    enumerates a folder and then loads, renames or moves the results must filter
    through this first.
    """
    return ":" not in path and "$" not in path


def scannable_assets(paths) -> list[str]:
    """list_assets() output with sub-objects and Verse digest paths removed."""
    return [p for p in paths if is_scannable_asset(p)]


def resolve_scan_path(scan_path: str) -> str:
    """
    Resolve an empty scan_path to the project's Content Browser mount point.

    Tools that default scan_path="" call this at runtime so they scan the user's
    project instead of /Game (which in UEFN is the entire Fortnite content tree
    and crashes the engine when iterated — Quirk #32).

    Pass a non-empty string to override (e.g. scan_path="/MyProject/Meshes").
    """
    if scan_path:
        return scan_path
    return f"/{detect_project_mount()}"


def resolve_content_path(path: str, default_subpath: str = "") -> str:
    """
    Resolve a destination path for assets a tool CREATES.

    The read-side counterpart is resolve_scan_path(). This one matters more,
    because a wrong scan path returns nothing while a wrong destination path
    produces assets the project cannot reference — every actor using them ends
    up with a dangling reference, which is how arena_generate left ~700 of them
    behind before it was fixed.

    In UEFN, /Game/ is Epic's Fortnite install, not the creator's project
    (UEFN_QUIRKS.md #23). Any /Game/ prefix is rewritten onto the project mount
    rather than trusted, so a caller passing one explicitly is corrected too.
    An empty path falls back to default_subpath under the mount.

    Resolved at call time — mount detection needs a live editor.
    """
    mount = f"/{detect_project_mount()}"
    if not path:
        return f"{mount}/{default_subpath}".rstrip("/")
    if path == "/Game" or path.startswith("/Game/"):
        return f"{mount}/{path[6:]}".rstrip("/")
    return path


def project_content_dir() -> str:
    """
    Return the user's project Content directory path on disk.

    unreal.Paths.project_content_dir() returns the FortniteGame *engine*
    content path in UEFN — not the user's island project.  This helper
    uses project_dir() + '/Content' which always resolves correctly.
    """
    root = unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.project_dir()
    ).rstrip("/\\")
    return root + "/Content"


# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────

_PREFIX = "[TOOLBELT]"


def log_info(message: str) -> None:
    unreal.log(f"{_PREFIX} {message}")


def log_warning(message: str) -> None:
    unreal.log_warning(f"{_PREFIX} {message}")


def log_error(message: str) -> None:
    unreal.log_error(f"{_PREFIX} {message}")


# ─────────────────────────────────────────────────────────────────────────────
#  Undo / Transaction
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def undo_transaction(label: str) -> Generator[None, None, None]:
    """
    Wraps all operations inside a single named undo transaction.
    """
    with unreal.ScopedEditorTransaction(label) as _t:
        try:
            yield
        except Exception as exc:
            log_error(f"Transaction '{label}' failed: {exc}")
            raise


# ─────────────────────────────────────────────────────────────────────────────
#  Actor Selection
# ─────────────────────────────────────────────────────────────────────────────

def get_selected_actors() -> list[unreal.Actor]:
    """Return a list of currently selected level actors (never None)."""
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = subsystem.get_selected_level_actors()
    return list(actors) if actors else []


def require_selection(min_count: int = 1) -> list[unreal.Actor] | None:
    """
    Return selected actors or log a warning and return None if too few.
    """
    actors = get_selected_actors()
    if len(actors) < min_count:
        msg = f"Select at least {min_count} actor(s) first."
        log_warning(msg)
        notify(msg)
        return None
    return actors


def get_selected_assets() -> list[unreal.Object]:
    """Return assets currently selected in the Content Browser (never None)."""
    try:
        assets = unreal.EditorUtilityLibrary.get_selected_assets()
        return list(assets) if assets else []
    except Exception:
        return []


def set_selected_actors(actors: list[unreal.Actor]) -> None:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    subsystem.set_selected_level_actors(actors)


# ─────────────────────────────────────────────────────────────────────────────
#  Asset Helpers
# ─────────────────────────────────────────────────────────────────────────────

def asset_tools() -> unreal.AssetTools:
    return unreal.AssetToolsHelpers.get_asset_tools()


def load_asset(path: str) -> unreal.Object | None:
    """Load an asset by content path. Returns None and logs on failure."""
    try:
        obj = unreal.EditorAssetLibrary.load_asset(path)
        if obj is None:
            log_warning(f"Asset not found: {path}")
        return obj
    except Exception as e:
        log_error(f"load_asset({path}): {e}")
        return None


def save_asset(path: str) -> bool:
    """Save asset by path. Returns True on success."""
    try:
        return unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
    except Exception as e:
        log_error(f"save_asset({path}): {e}")
        return False


def ensure_folder(path: str) -> None:
    """Create a Content Browser folder if it doesn't exist."""
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)
        log_info(f"Created folder: {path}")


def create_material_instance(
    parent_path: str,
    instance_name: str,
    package_path: str,
) -> unreal.MaterialInstanceConstant | None:
    """
    Create a MaterialInstanceConstant from a parent material.

    The parent is assigned AFTER creation, via MaterialEditingLibrary. UE 6.0
    dropped the factory's initial_parent attribute, and setting it raised

        AttributeError: 'MaterialInstanceConstantFactoryNew' object has no
        attribute 'initial_parent'

    which took every Materials tool down on UEFN 42.00 — the whole category, for
    anyone on the current engine. set_material_instance_parent() is the
    supported route and works on both.

    Returns None on failure; never a parentless instance, because a material
    instance with no parent silently renders as the engine default and looks
    like the tool merely picked bad colours.
    """
    parent = load_asset(parent_path)
    if parent is None:
        return None

    ensure_folder(package_path)
    full_path = f"{package_path}/{instance_name}"

    # Delete pre-existing asset so we can overwrite
    if unreal.EditorAssetLibrary.does_asset_exist(full_path):
        unreal.EditorAssetLibrary.delete_asset(full_path)

    mi = asset_tools().create_asset(instance_name, package_path,
                                    unreal.MaterialInstanceConstant,
                                    unreal.MaterialInstanceConstantFactoryNew())
    if mi is None:
        log_error(f"Failed to create material instance: {full_path}")
        return None

    try:
        unreal.MaterialEditingLibrary.set_material_instance_parent(mi, parent)
    except Exception as e:
        # Better to have no asset than one that quietly renders as the default.
        log_error(
            f"Could not set parent '{parent_path}' on {full_path}: "
            f"{type(e).__name__}: {e}"
        )
        unreal.EditorAssetLibrary.delete_asset(full_path)
        return None

    return mi



def set_mi_scalar(mi: unreal.MaterialInstanceConstant, name: str, value: float) -> None:
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, name, value)


def set_mi_vector(mi: unreal.MaterialInstanceConstant, name: str, color: unreal.LinearColor) -> None:
    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, name, color)


def set_mi_texture(mi: unreal.MaterialInstanceConstant, name: str, tex: unreal.Texture) -> None:
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi, name, tex)


# ─────────────────────────────────────────────────────────────────────────────
#  UI Notifications
# ─────────────────────────────────────────────────────────────────────────────

def notify(message: str, duration: float = 4.0) -> None:
    """Show a Slate notification in the editor viewport."""
    try:
        unreal.SystemLibrary.print_string(
            None, f"[Toolbelt] {message}",
            print_to_screen=True, print_to_log=False,
            text_color=unreal.LinearColor(0.2, 1.0, 0.4, 1.0),
            duration=duration,
        )
    except Exception:
        pass
    log_info(message)


# ─────────────────────────────────────────────────────────────────────────────
#  Progress Bar (slow-task wrapper)
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def with_progress(items: Iterable, label: str, total: int | None = None):
    """
    Display a slow-task progress bar while iterating.
    """
    items = list(items)
    count = total or len(items)

    with unreal.ScopedSlowTask(count, label) as task:
        task.make_dialog(True)  # show cancel button

        def _gen():
            for item in items:
                if task.should_cancel():
                    log_info(f"{label} — cancelled.")
                    return
                task.enter_progress_frame(1)
                yield item

        yield _gen()


# ─────────────────────────────────────────────────────────────────────────────
#  Math Helpers
# ─────────────────────────────────────────────────────────────────────────────

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rand_vec(x_range=(-100, 100), y_range=(-100, 100), z_range=(0, 0)) -> unreal.Vector:
    return unreal.Vector(
        random.uniform(*x_range),
        random.uniform(*y_range),
        random.uniform(*z_range),
    )


def color_from_hex(hex_str: str) -> unreal.LinearColor:
    """
    Parse "#RRGGBB" or "RRGGBB" hex string to LinearColor.
    """
    hex_str = hex_str.lstrip("#")
    if len(hex_str) not in (6, 8):
        log_warning(f"color_from_hex: expected 6 or 8 hex digits, got '{hex_str}'")
        return unreal.LinearColor(1, 1, 1, 1)

    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    a = int(hex_str[6:8], 16) / 255.0 if len(hex_str) == 8 else 1.0

    # sRGB → linear approximation
    def to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return unreal.LinearColor(to_linear(r), to_linear(g), to_linear(b), a)


def actors_bounding_box(
    actors: list[unreal.Actor],
) -> tuple[unreal.Vector, unreal.Vector]:
    """
    Return (min_point, max_point) of the axis-aligned bounding box.
    """
    if not actors:
        raise ValueError("actors_bounding_box requires at least one actor.")
    xs, ys, zs = [], [], []
    for a in actors:
        loc = a.get_actor_location()
        xs.append(loc.x)
        ys.append(loc.y)
        zs.append(loc.z)
    return (
        unreal.Vector(min(xs), min(ys), min(zs)),
        unreal.Vector(max(xs), max(ys), max(zs)),
    )


def spawn_static_mesh_actor(
    mesh_path: str,
    location: unreal.Vector,
    rotation: unreal.Rotator | None = None,
    scale: unreal.Vector | None = None,
) -> unreal.StaticMeshActor | None:
    """
    Convenience: spawn a StaticMeshActor and assign a mesh in one call.
    """
    mesh = load_asset(mesh_path)
    if mesh is None or not isinstance(mesh, unreal.StaticMesh):
        log_error(f"spawn_static_mesh_actor: '{mesh_path}' is not a valid StaticMesh.")
        return None

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    rotation = rotation or unreal.Rotator(0, 0, 0)
    actor: unreal.StaticMeshActor = actor_sub.spawn_actor_from_class(
        unreal.StaticMeshActor, location, rotation
    )
    if actor is None:
        log_error("spawn_static_mesh_actor: spawn_actor_from_class returned None.")
        return None

    actor.static_mesh_component.set_static_mesh(mesh)
    if scale:
        actor.set_actor_scale3d(scale)

    return actor

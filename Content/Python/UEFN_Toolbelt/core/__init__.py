"""
UEFN TOOLBELT — Core Utilities
========================================
Shared helpers used by every tool module.
"""

from __future__ import annotations

import contextlib
import math
import random
from typing import Generator, Iterable, List, Optional

import unreal

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

def get_selected_actors() -> List[unreal.Actor]:
    """Return a list of currently selected level actors (never None)."""
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = subsystem.get_selected_level_actors()
    return list(actors) if actors else []


def require_selection(min_count: int = 1) -> Optional[List[unreal.Actor]]:
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


def get_selected_assets() -> List[unreal.Object]:
    """Return assets currently selected in the Content Browser (never None)."""
    try:
        assets = unreal.EditorUtilityLibrary.get_selected_assets()
        return list(assets) if assets else []
    except Exception:
        return []


def set_selected_actors(actors: List[unreal.Actor]) -> None:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    subsystem.set_selected_level_actors(actors)


# ─────────────────────────────────────────────────────────────────────────────
#  Asset Helpers
# ─────────────────────────────────────────────────────────────────────────────

def asset_tools() -> unreal.AssetTools:
    return unreal.AssetToolsHelpers.get_asset_tools()


def load_asset(path: str) -> Optional[unreal.Object]:
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
) -> Optional[unreal.MaterialInstanceConstant]:
    """
    Create a MaterialInstanceConstant from a parent material.
    """
    parent = load_asset(parent_path)
    if parent is None:
        return None

    factory = unreal.MaterialInstanceConstantFactoryNew()
    factory.initial_parent = parent

    ensure_folder(package_path)
    full_path = f"{package_path}/{instance_name}"

    # Delete pre-existing asset so we can overwrite
    if unreal.EditorAssetLibrary.does_asset_exist(full_path):
        unreal.EditorAssetLibrary.delete_asset(full_path)

    mi = asset_tools().create_asset(instance_name, package_path,
                                    unreal.MaterialInstanceConstant, factory)
    if mi is None:
        log_error(f"Failed to create material instance: {full_path}")
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
def with_progress(items: Iterable, label: str, total: Optional[int] = None):
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
    actors: List[unreal.Actor],
) -> "tuple[unreal.Vector, unreal.Vector]":
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
    rotation: Optional[unreal.Rotator] = None,
    scale: Optional[unreal.Vector] = None,
) -> Optional[unreal.StaticMeshActor]:
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

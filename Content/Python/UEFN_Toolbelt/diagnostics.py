
import unreal

from .registry import register_tool


@register_tool(
    name="debug_dump_verse_actor",
    category="Utilities",
    description="Dump all internal properties of a selected Verse actor for discovery.",
    tags=["debug", "verse", "discovery"],
)
def dump_actor_info(**kwargs) -> dict:
    sel = unreal.EditorLevelLibrary.get_selected_level_actors()
    if not sel:
        unreal.log_warning("[DIAGNOSTIC] No actor selected.")
        return {"status": "error", "message": "No actor selected."}

    actor = sel[0]
    unreal.log(f"[DIAGNOSTIC] Actor Label: {actor.get_actor_label()}")
    unreal.log(f"[DIAGNOSTIC] Actor Full Name: {actor.get_full_name()}")
    unreal.log(f"[DIAGNOSTIC] Class Name: {actor.get_class().get_name()}")
    unreal.log(f"[DIAGNOSTIC] Class Path: {actor.get_class().get_path_name()}")

    # 1. Inspect Class Hierarchy
    unreal.log("[DIAGNOSTIC] Class Hierarchy:")
    try:
        curr_cls = actor.get_class()
        while curr_cls:
            unreal.log(f"  <- {curr_cls.get_name()} ({curr_cls.get_path_name()})")
            # In Unreal Python, it is get_super_class()
            if hasattr(curr_cls, "get_super_class"):
                curr_cls = curr_cls.get_super_class()
            else:
                break
    except Exception as e:
        unreal.log_warning(f"  Class hierarchy inspection failed: {e}")

    # 2. Inspect Components
    unreal.log("[DIAGNOSTIC] Inspecting Components...")
    try:
        # Get all components using the standard Unreal method
        components = actor.get_components_by_class(unreal.ActorComponent)
        for comp in components:
            unreal.log(f"  • Component: {comp.get_name()} (Class: {comp.get_class().get_name()})")
            # If it's a Verse-related component, dump its properties
            if "verse" in comp.get_class().get_name().lower():
                unreal.log(f"    - Full Path: {comp.get_class().get_path_name()}")
    except Exception as e:
        unreal.log_warning(f"  Failed to get components: {e}")

    # 3. Aggressive property dump (all strings)
    unreal.log("[DIAGNOSTIC] Aggressive String Search in Properties...")
    # Safe alternative to inspect.getmembers on Unreal objects
    for name in dir(actor):
        if name.startswith(("__", "get_", "set_")):
            continue
        try:
            value = getattr(actor, name)
            s_val = str(value)
            # If the name or value contains "hello" or "verse", highlight it
            if "hello" in name.lower() or "hello" in s_val.lower() or "verse" in name.lower() or "verse" in s_val.lower():
                unreal.log(f"  [MATCH] {name}: {s_val}")
        except Exception:
            pass

    # 4. Check specific internal Verse fields
    unreal.log("[DIAGNOSTIC] Checking known Verse-internal fields...")
    try:
        # These are often used in UEFN 5.1+
        if hasattr(actor, "ScriptClass"):
             unreal.log(f"  • ScriptClass: {actor.ScriptClass}")
        if hasattr(actor, "VerseClass"):
             unreal.log(f"  • VerseClass: {actor.VerseClass}")
    except Exception:
        pass

    unreal.log("[DIAGNOSTIC] Dump Complete.")
    return {"status": "ok", "actor": actor.get_actor_label()}

@register_tool(
    name="debug_audit_verse_assets",
    category="Utilities",
    description="Search the project asset registry for all Verse-generated Blueprints.",
    tags=["debug", "verse", "audit"],
)
def audit_verse_assets(**kwargs) -> dict:
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    unreal.log("[ASSET AUDIT] Searching for Verse-related assets...")

    # Search for anything in the project content
    filter = unreal.ARFilter(package_paths=["/TOOL_TEST"], recursive_paths=True)
    assets = ar.get_assets(filter)

    found = False
    for asset in assets:
        name = str(asset.asset_name)
        # Class path is now a TopLevelAssetPath in 5.1+
        cls = str(asset.asset_class_path.asset_name)
        if "hello" in name.lower() or "verse" in name.lower() or "device" in name.lower():
            # Skip the base VerseDevice class
            if name == "VerseDevice" or name == "CreativeDevice":
                continue
            unreal.log(f"  • Asset: {name} (Class: {cls})")
            unreal.log(f"    - Path: {asset.package_name}")
            found = True

    if not found:
        unreal.log_warning("[ASSET AUDIT] No student Verse assets found in /TOOL_TEST. Ensure Verse is compiled.")

    return {"status": "ok", "found": found}

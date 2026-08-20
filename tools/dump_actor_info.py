
import unreal

from ..registry import register_tool


@register_tool(
    name="debug_dump_verse_actor",
    category="Utilities",
    description="Dump all internal properties of a selected Verse actor for discovery.",
    tags=["debug", "verse", "discovery"],
)
def dump_actor_info(**kwargs):
    sel = unreal.EditorLevelLibrary.get_selected_level_actors()
    if not sel:
        print("[DIAGNOSTIC] No actor selected.")
        return

    actor = sel[0]
    print(f"[DIAGNOSTIC] Actor: {actor.get_actor_label()}")
    print(f"[DIAGNOSTIC] Class: {actor.get_class().get_name()}")
    print(f"[DIAGNOSTIC] Class Path: {actor.get_class().get_path_name()}")

    # 1. Try to list all tags
    print(f"[DIAGNOSTIC] Tags: {actor.tags}")

    # 2. Try to list all editor properties
    print("[DIAGNOSTIC] Listing all accessible editor properties...")
    try:
        _props = unreal.EditorLevelLibrary.get_all_level_actors()[0].get_class().get_name() # just to check lib
        for prop in actor.get_class().list_properties():
            try:
                val = actor.get_editor_property(prop.get_name())
                print(f"  • {prop.get_name()}: {val}")
            except Exception:
                pass
    except Exception as e:
        print(f"[DIAGNOSTIC] Property listing failed: {e}")

    # 3. Check for Verse specific attributes
    print("[DIAGNOSTIC] Checking for Verse attributes...")
    for attr in dir(actor):
        if "verse" in attr.lower() or "class" in attr.lower():
            try:
                val = getattr(actor, attr)
                print(f"  • {attr}: {val}")
            except Exception:
                pass

if __name__ == "__main__":
    dump_actor_info()

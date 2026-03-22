# 🗺️ UEFN Schema Explorer: The High-Fidelity API Guide

This document "dissects" the **1.6MB Reference Schema** (`uefn_reference_schema.json`) for engineers and creators. It translates the raw JSON data into actionable knowledge for building smarter UEFN automation.

---

## 📊 The "Big Picture" Stats

- **Total Discoverable Classes**: 14 (Unique classes found in the level context)
- **Total UPROPERTIES**: 1,031 (Boolean switches, Floats, Vectors, etc.)
- **Total Discoverable Methods**: 3,485 (Functions accessible via Python/Verse)

### Top 5 Property-Heavy Classes
| Class | Properties | Why it matters |
| :--- | :--- | :--- |
| `BuildingProp` | 149 | The base of all placement logic. |
| `FortCreativeDeviceProp` | 149 | The gatekeeper to Verse logic. |
| `BuildingFloor` | 144 | Critical for grid-snapping and voxelization. |
| `FortMinigameSettingsBuilding` | 72 | Controls Game Settings in-session. |
| `FortPlayerStartCreative` | 59 | Essential for spawn-point automation. |

---

## 🧠 For Engineers: How to use the Schema

### 1. Zero-Friction Property Access
The Toolbelt uses `schema_utils.py` to validate your scripts at runtime.
```python
from UEFN_Toolbelt import schema_utils

# Check if a property exists and is readable
res = schema_utils.validate_property("Actor", "actor_guid")
if res["exists"] and res["meta"]["readable"]:
    # Safe to use!
```

### 2. Multi-Component Discovery
The schema reveals that an "Actor" is more than just its label. You can now target:
- **`BillboardComponent`**: For icon scaling/visibility.
- **`DecalComponent`**: For universal material painting.
- **`SkeletalMeshComponent`**: For 1.6MB accurate character rigging.

### 3. Read-Only Guards
Stop hunting for silent failures. The schema marks properties like `_wrapper_meta_data` as `readable: false`, so our tools can warn you *before* the crash.

---

## 🎨 For Non-Technical Creators

**"How does this make my AI smarter?"**
By "feeding" this schema into an AI (like Claude or Antigravity), the AI stops guessing. It knows the **exact** name of the setting you want to change (e.g., `bIsEnabled` instead of `IsActive`).

**One-Click Brain Sync**:
Every time you add a new Verse device, use the **"Sync Level Schema to AI"** button in the Dashboard. It updates your local documentation instantly.

---

---
 
 ## 🛤️ Simulation & Sequences (Phase 19 COMPLETE)

 Phase 19 has successfully operationalized the schema with:
 - **Simulation Proxies**: Python handlers generated directly from schema method discovery.
 - **Named Auto-Link**: Robust fuzzy resolution that maps viewport actors to Verse classes when the formal API is invisible.
 - **Sequencer Automation**: One-click level sequence generation for any schema-validated actor.

 > [!IMPORTANT]
 > For a deep dive into the technical hurdles overcome in this phase, see **[docs/UEFN_QUIRKS.md](docs/UEFN_QUIRKS.md)**.

---

## 🤖 AI-Agent Readiness (Phase 20 COMPLETE)

Phase 20 makes the schema the backbone of the entire toolbelt — not just a reference, but the live source of truth that every tool queries.

### What Changed

**`schema_utils.py` — New Functions**

| Function | Purpose |
| :--- | :--- |
| `discover_properties(class_name)` | Returns all schema-known properties for a class as `{name: meta_dict}`. Replaces hardcoded property name lists across tools — tools are now correct-by-construction for any class in the schema. |
| `list_classes()` | Returns every class name in the reference schema. Use this to browse what the schema knows without loading the full 1.6MB JSON. |

**Why This Matters**

Before Phase 20, tools like `verse_device_editor`'s property reader contained a hardcoded list of 11 common property names:
```python
# Before — hardcoded, misses everything not on this list
common_props = ["bIsEnabled", "bVisible", "TeamIndex", ...]
```
After Phase 20, it queries the schema:
```python
# After — correct for any class the schema knows about
schema_props = schema_utils.discover_properties(class_name)
prop_names = list(schema_props.keys()) if schema_props else _FALLBACK_PROPS
```

### The Tool Manifest — Machine-Readable Tool Index

Run `tb.run("plugin_export_manifest")` to generate `Saved/UEFN_Toolbelt/tool_manifest.json`.

This file is the **single most important artifact for AI-agent automation**. It contains every registered tool with its full Python parameter signature, introspected via `inspect.signature()` at export time:

```json
{
  "verse_list_devices": {
    "name": "verse_list_devices",
    "category": "Verse Helpers",
    "description": "List all Verse/Creative device actors in the current level.",
    "tags": ["verse", "device", "list", "enumerate"],
    "parameters": {
      "name_filter": {"type": "str", "required": false, "default": ""}
    }
  }
}
```

An AI agent with access to `tool_manifest.json` and the MCP bridge can autonomously:
1. Read the manifest to discover available tools and their parameter contracts
2. Call tools via `run_tool` with correct arguments (no guessing required)
3. Read structured dict returns to make decisions based on results
4. Chain tool calls: `snapshot_save` → bulk edit → `snapshot_compare_live` → verify

### Structured Returns — The Full MCP Loop

Before Phase 20, most tools returned `None`. After Phase 20, 25+ tools return structured dicts:

```python
# What an AI agent sees via MCP now:
result = ue.run_tool("verse_list_devices")
# → {"status": "ok", "count": 4, "devices": [{"label": ..., "class": ..., "location": ...}]}

result = ue.run_tool("snapshot_diff", name_a="before", name_b="after")
# → {"status": "ok", "added_count": 3, "removed_count": 0, "moved_count": 7, "moved": [...]}

result = ue.run_tool("tag_search", tag_name="hero_prop", folder="/Game")
# → {"status": "ok", "count": 12, "matches": ["/Game/Props/...", ...]}
```

The complete chain is verified end-to-end:
**tool returns dict → `registry.execute()` → `_serialize(result)` → JSON in MCP response → Claude Code reads it**

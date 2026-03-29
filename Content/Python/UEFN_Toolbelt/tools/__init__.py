"""
UEFN TOOLBELT — Tools Package
========================================
Each import here triggers the module's @register_tool decorators, which
automatically adds the tool to the global ToolRegistry.

To add a new tool:
  1. Create tools/my_tool.py with a @register_tool-decorated entry function.
  2. Add:  from . import my_tool    ← right here.
  Done.
"""

from . import integration_test
from . import material_master
from . import arena_generator
from . import spline_prop_placer
from . import bulk_operations
from . import verse_device_editor
from . import smart_importer
from . import verse_snippet_generator
from . import text_painter
from . import asset_renamer
from . import foliage_tools
from . import lod_tools
from . import spline_to_verse
from . import project_scaffold
from . import memory_profiler
from . import api_explorer
from . import prop_patterns
from . import reference_auditor
from . import level_snapshot
from . import asset_tagger
from . import screenshot_tools
from . import plugin_manager
from . import api_capability_crawler
from . import mcp_bridge
from . import smart_organizer
from . import system_perf
from . import asset_importer
from . import procedural_geometry
from . import text_voxelizer
from . import verse_schema
from . import system_build
from . import measurement_tools
from . import localization_tools
from . import foliage_converter
from . import entity_kits
from . import selection_utils
from . import project_admin
from . import publish_audit
from . import lighting_mastery
from . import sequencer_tools
from . import sim_device_proxy
from . import config_tools
from . import verse_device_graph
from . import project_setup
from . import sign_tools
from . import actor_org_tools
from . import advanced_alignment
from . import zone_tools
from . import proximity_tools
from . import postprocess_tools
from . import audio_tools
from . import optimization_tools
from . import prefab_migrator
from . import ui_icon_import
from . import level_health
from . import prefab_stamp
from . import activity_log_tools
from . import niagara_tools
from . import pcg_tools
from . import geometry_tools
from . import movie_render_tools
from . import viewport_tools
from . import actor_visibility
from . import verse_templates
from . import cooker_optimizer

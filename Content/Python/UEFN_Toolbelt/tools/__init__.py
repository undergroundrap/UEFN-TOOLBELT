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
from . import mcp_bridge

import os
import re
import json
import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning

class VerseSchemaParser:
    """
    Parses Verse .digest files (fortnite.digest, verse.digest, unreal.digest)
    to build a native schema of device types and properties.
    """
    
    def __init__(self):
        self.device_schemas = {}
        self.loaded = False
        self.load_digests()

    def load_digests(self):
        """Finds and parses all .digest files in the project."""
        # Robust root resolution: Walk up until we find 'Content'
        curr = os.path.abspath(__file__)
        proj_root = None
        while curr and os.path.dirname(curr) != curr:
            curr = os.path.dirname(curr)
            if os.path.basename(curr) == "Content":
                proj_root = os.path.dirname(curr)
                break
        
        if not proj_root:
            proj_root = unreal.Paths.project_dir()

        # UEFN 5.4+ often stores digests in the Local AppData folder
        appdata = os.path.expandvars("%LOCALAPPDATA%")
        saved_verse = os.path.join(appdata, "UnrealEditorFortnite", "Saved", "VerseProject")
        
        search_paths = [
            proj_root,
            os.path.join(proj_root, ".verse"), 
            saved_verse,
            unreal.Paths.project_content_dir(),
            unreal.Paths.project_plugins_dir(),
            unreal.Paths.project_intermediate_dir(),
            unreal.Paths.engine_dir(),
            unreal.Paths.engine_content_dir(),
            unreal.Paths.engine_plugins_dir()
        ]
        
        search_paths = list(set([os.path.abspath(p) for p in search_paths if p and os.path.exists(p)]))
        
        digest_files = []
        for path in search_paths:
            for root, _, files in os.walk(path):
                if ".git" in root or "Binaries" in root or "Build" in root:
                    continue
                for file in files:
                    lower_file = file.lower()
                    if "digest" in lower_file:
                        if lower_file.endswith(".verse") or lower_file.endswith(".digest"):
                            digest_files.append(os.path.join(root, file))
        
        for file in set(digest_files):
            try:
                self._parse_file(file)
            except Exception as e:
                log_warning(f"Failed to parse digest {file}: {str(e)}")
        
        self.loaded = True
        log_info(f"Verse Schema updated: {len(self.device_schemas)} definitions loaded.")

    def _parse_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        lines = content.splitlines()
        current_class = None
        base_indent = 0
        
        # Regex patterns from FortniteForge logic
        # Regex patterns - handling <public>, <concrete>, etc. more robustly
        # class_pattern: name<visibility> := class<specifiers>(parent)
        class_pattern = re.compile(r'^(\w+)(?:<[^>]+>)?\s*:=\s*class(?:<[^>]+>)*\s*\(([^)]*)\)')
        # prop_pattern: name<visibility> : type = default
        prop_pattern = re.compile(r'^(\w+)(?:<[^>]+>)?\s*:\s*([^:=]+?)(?:\s*=\s*(.+))?$')

        for line in lines:
            trimmed = line.lstrip()
            if not trimmed or trimmed.startswith("#") or trimmed.startswith("//"):
                continue
            
            indent = len(line) - len(trimmed)
            
            # Detect class
            class_match = class_pattern.match(trimmed)
            if class_match:
                class_name = class_match.group(1)
                parent_name = class_match.group(2)
                current_class = {
                    "name": class_name,
                    "parent": parent_name,
                    "properties": {},
                    "events": [],
                    "functions": []
                }
                self.device_schemas[class_name] = current_class
                base_indent = indent
                continue
            
            # Detect members
            if current_class and indent > base_indent:
                prop_match = prop_pattern.match(trimmed)
                if prop_match:
                    name = prop_match.group(1)
                    prop_type = prop_match.group(2).strip()
                    
                    if "event" in prop_type or "listenable" in prop_type:
                        current_class["events"].append(name)
                    elif "(" in prop_type and ")" in prop_type:
                        current_class["functions"].append(name)
                    else:
                        current_class["properties"][name] = prop_type
            elif current_class and indent <= base_indent:
                current_class = None

    def get_schema(self, class_name):
        if not self.loaded:
            self.load_digests()
        return self.device_schemas.get(class_name)

_parser = VerseSchemaParser()

@register_tool(name="api_verse_get_schema", category="Verse Helpers")
def api_verse_get_schema(class_name: str) -> dict:
    """
    Returns the Verse schema (properties, events, functions) for a given class.
    Derived from .digest.verse intelligence.
    """
    schema = _parser.get_schema(class_name)
    if not schema:
        # Try fuzzy match
        normalized = class_name.replace("_C", "").replace("BP_", "")
        schema = _parser.get_schema(normalized)

    if schema:
        log_info(f"Schema for {class_name}: {len(schema['properties'])} props, {len(schema['events'])} events.")
        return {"status": "ok", "class_name": class_name, "schema": schema}

    log_warning(f"No Verse schema found for {class_name}. Ensure Verse is compiled.")
    return {"status": "error", "class_name": class_name, "schema": None}

@register_tool(name="api_verse_refresh_schemas", category="Verse Helpers")
def api_verse_refresh_schemas() -> dict:
    """Forces a re-scan of all Verse digest files for schema intelligence."""
    _parser.load_digests()
    return {"status": "ok", "loaded": len(_parser.device_schemas)}

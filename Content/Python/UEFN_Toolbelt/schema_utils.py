"""
UEFN TOOLBELT — Schema Utilities
========================================
Helper functions to query the 1.6MB High-Fidelity Schema for
runtime validation and property intelligence.
"""

import json
import os
from typing import Any

import unreal

_SCHEMA_CACHE: dict[str, Any] = {}

def get_schema_path() -> str:
    """Find the reference schema in the project docs."""
    curr = os.path.abspath(__file__)
    project_root = None
    while curr and os.path.dirname(curr) != curr:
        curr = os.path.dirname(curr)
        if os.path.basename(curr) == "Content":
            project_root = os.path.dirname(curr)
            break

    if not project_root:
        project_root = unreal.Paths.project_dir()

    return os.path.join(project_root, "docs", "uefn_reference_schema.json")


def load_schema() -> dict[str, Any]:
    """Load the full reference schema into memory (cached)."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE:
        return _SCHEMA_CACHE

    path = get_schema_path()
    if not os.path.exists(path):
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            _SCHEMA_CACHE = json.load(f)
            return _SCHEMA_CACHE
    except Exception:
        return {}


def get_class_info(class_name: str) -> dict[str, Any] | None:
    """Get the schema definition for a specific class."""
    schema = load_schema()
    return schema.get("classes", {}).get(class_name)


def validate_property(class_name: str, property_name: str) -> dict[str, Any]:
    """
    Check if a property exists on a class and return its metadata.
    Returns {"exists": False} if not found.
    """
    info = get_class_info(class_name)
    if not info:
        return {"exists": False}

    meta = info.get("properties", {}).get(property_name)
    if not meta:
        return {"exists": False}

    return {"exists": True, "meta": meta}


def list_classes() -> list:
    """Return all class names defined in the reference schema."""
    schema = load_schema()
    return list(schema.get("classes", {}).keys())


def discover_properties(class_name: str) -> dict[str, Any]:
    """
    Return all schema-known properties for a class as {name: meta_dict}.
    Returns an empty dict if the class isn't in the reference schema.
    Useful for replacing hardcoded property name lists with live schema data.
    """
    info = get_class_info(class_name)
    if not info:
        return {}
    return info.get("properties", {})

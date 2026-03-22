---
name: Community Plugin Submission
about: Submit your plugin for listing in the Plugin Hub
title: "plugin: "
labels: community-plugin
assignees: undergroundrap
---

## Plugin name
<!-- The display name shown in the Plugin Hub -->

## What it does
<!-- One paragraph description -->

## Plugin details

| Field | Value |
|---|---|
| Author | |
| GitHub URL | |
| Download URL (raw .py) | |
| Category | |
| Min Toolbelt version | 1.5.3 |
| File size (KB) | |

## Security checklist
- [ ] Single `.py` file, ≤ 50 KB
- [ ] No `subprocess`, `socket`, `ctypes`, or network library imports
- [ ] Uses `@register_tool` decorator
- [ ] Returns a dict with `status` key
- [ ] Tested in live UEFN editor with the hard refresh bundle

## registry.json entry
```json
{
  "id": "",
  "name": "",
  "version": "1.0.0",
  "author": "",
  "author_url": "",
  "type": "community",
  "description": "",
  "category": "",
  "tags": [],
  "url": "",
  "download_url": "",
  "min_toolbelt_version": "1.5.3",
  "size_kb": 0
}
```

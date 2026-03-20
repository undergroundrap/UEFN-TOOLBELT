import os
import ast
import json

root = os.path.join(os.path.dirname(__file__), "Content", "Python", "UEFN_Toolbelt", "tools")
tools = []

for file in os.listdir(root):
    if not file.endswith(".py") or file == "__init__.py": continue
    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except Exception:
            continue
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, 'id', '') == 'register_tool':
                    tool_info = {'source_file': file, 'name': 'unknown', 'category': 'unknown', 'description': 'No description.'}
                    for kw in dec.keywords:
                        if kw.arg == 'name':
                            tool_info['name'] = getattr(kw.value, 'value', getattr(kw.value, 's', getattr(kw.value, 'id', '')))
                        elif kw.arg == 'category':
                            tool_info['category'] = getattr(kw.value, 'value', getattr(kw.value, 's', getattr(kw.value, 'id', '')))
                    
                    doc = ast.get_docstring(node)
                    if doc:
                        tool_info['description'] = doc.split("\n")[0]
                    tools.append(tool_info)

out_path = os.path.join(os.path.dirname(__file__), "tools_dump.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(tools, f, indent=2)

import os
import re

cd = r'c:\Users\ocean\AntigravityProjects\UEFN-TOOLBELT\Content\Python\UEFN_Toolbelt'

all_tools = set()
for root, _, files in os.walk(os.path.join(cd, 'tools')):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                text = f.read()
                matches = re.findall(r'@register_tool\s*\(\s*name=[\'"]([^\'"]+)[\'"]', text)
                all_tools.update(matches)

print(f"Total tools matched: {len(all_tools)}")

covered_tools = set()

with open(r'c:\Users\ocean\AntigravityProjects\UEFN-TOOLBELT\tests\smoke_test.py', 'r', encoding='utf-8') as f:
    text = f.read()
    covered_tools.update(re.findall(r'run\s*\(\s*[\'"]([^\'"]+)[\'"]', text))

with open(os.path.join(cd, 'tools', 'integration_test.py'), 'r', encoding='utf-8') as f:
    text = f.read()
    covered_tools.update(re.findall(r'run\s*\(\s*[\'"]([^\'"]+)[\'"]', text))

uncovered = sorted(list(all_tools - covered_tools))
print(f"Uncovered tools ({len(uncovered)}):")
for t in uncovered:
    print(f"  {t}")

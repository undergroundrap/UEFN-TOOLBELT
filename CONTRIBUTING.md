# Contributing to UEFN Toolbelt

Thanks for wanting to contribute. Here's everything you need.

---

## Ways to Contribute

| Type | How |
|---|---|
| Bug report | Open an issue using the Bug Report template |
| Feature request | Open an issue using the Feature Request template |
| New community plugin | Add an entry to `registry.json` and open a PR |
| Core tool contribution | Fork → add `.py` to `tools/` → PR |
| Docs improvement | Edit any `.md` file and open a PR |

---

## Adding a Community Plugin (Path A — recommended)

1. **Host your `.py` file** in your own GitHub repo (single file, ≤ 50 KB, no zips).
2. **Fork** this repository.
3. **Add your entry** to `registry.json` at the root:

```json
{
  "id": "your_tool_id",
  "name": "Your Tool Name",
  "version": "1.0.0",
  "author": "Your Name",
  "author_url": "https://github.com/yourhandle",
  "type": "community",
  "description": "One sentence description.",
  "category": "Gameplay",
  "tags": ["tag1", "tag2"],
  "url": "https://github.com/yourhandle/yourrepo/blob/main/your_tool.py",
  "download_url": "https://raw.githubusercontent.com/yourhandle/yourrepo/main/your_tool.py",
  "min_toolbelt_version": "1.5.3",
  "size_kb": 10
}
```

4. **Open a PR** — once merged, your tool appears in every user's Plugin Hub on next Refresh.

**Requirements for community plugins:**
- Single `.py` file, ≤ 50 KB
- Passes the four-gate security scanner (no `subprocess`, `socket`, `ctypes`, network libs)
- Uses `@register_tool` decorator with `name`, `category`, `description`
- Returns a `dict` with at least `{"status": "ok"}` or `{"status": "error", "error": "..."}`

---

## Contributing a Core Tool (Path B)

1. Fork the repository.
2. Create your tool in `Content/Python/UEFN_Toolbelt/tools/your_tool.py`.
3. Import it in `Content/Python/UEFN_Toolbelt/tools/__init__.py`.
4. Add it to the hot-reload list in `launcher.py`.
5. Run the syntax check: `python -c "import ast; ast.parse(open('Content/Python/UEFN_Toolbelt/tools/your_tool.py').read())"`
6. Test in the live UEFN editor with the hard refresh bundle (see README).
7. Open a PR describing what the tool does and how you tested it.

**Core tool requirements:**
- All tools return structured dicts: `{"status": "ok", "count": N, "data": [...]}`
- Tool names use `snake_case`
- No hardcoded file paths — use `unreal.Paths.*` APIs
- No blocking `time.sleep()` calls — UEFN main thread must stay free

---

## Git Commit Format

```
type: concise description in lowercase
```

Types: `feat` · `fix` · `docs` · `refactor` · `test` · `perf`

Examples:
```
feat: wave spawner tool with verse device integration
fix: mcp bridge port binding on windows firewall block
docs: plugin hub onboarding guide
```

---

## Two-Phase Validation (required before every PR)

**Phase 1 — syntax check (run locally):**
```bash
python -c "import ast; ast.parse(open('path/to/your_file.py', encoding='utf-8').read()); print('OK')"
```

**Phase 2 — live UEFN test (required):**
```python
import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
```

PRs that haven't been tested in the live editor will be asked to verify before merge.

---

## Code of Conduct

Be respectful, constructive, and collaborative. This project is for the UEFN community.
Harassment or abuse of any kind will result in immediate removal.

---

**Questions?** Open an issue or reach out via GitHub.

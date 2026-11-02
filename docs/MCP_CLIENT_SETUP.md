# Connect an AI client to UEFN, once

Register Toolbelt's MCP server once per client, at user level. After that,
every ordinary local chat in that client can reach UEFN, in any project folder,
with no per-project `.mcp.json`.

**What has been checked.** On 2026-11-01, on Windows 11 with UEFN
`Release-43.00-CL-59596594`, a read-only check passed in two clients registered
this way: the **Claude desktop app's Code tab** (Claude Code) and the **Codex
desktop app**. The check covered connection, `ping`, the first page of
`list_toolbelt_tools` and the first page of `get_all_actors`, and every reply
arrived inline. **Not yet checked through an MCP client:** tools that change the
level, later pages, maximum-size replies, Claude Desktop's Chat surface, and
other clients.

## 1. Prepare an interpreter (once)

`mcp_server.py` runs outside UEFN, in an ordinary Python 3 that has the `mcp`
package. The editor's embedded Python is not used for this.

```bat
python -m pip install mcp
```

Note the full path of that interpreter (for example from `where python`). On
Windows, use the full path in the commands below, not plain `python`, because
the `python` that a client starts may differ from the one in your terminal.

## 2. Register Toolbelt (once per client)

Replace both paths with your own. `-B` keeps Python from writing `__pycache__`
into your clone.

**Claude Code**, including the Claude desktop app's Code tab:

```bat
claude mcp add --scope user uefn-toolbelt -- C:\path\to\python.exe -B C:\path\to\UEFN-TOOLBELT\mcp_server.py
```

`--scope user` makes the server available in all your projects. Without it,
Claude Code registers it for the current folder only.

**Codex** (the Codex CLI and the Codex desktop app share this user-level
configuration):

```bat
codex mcp add uefn-toolbelt -- C:\path\to\python.exe -B C:\path\to\UEFN-TOOLBELT\mcp_server.py
```

Neither command needs a port, a token or an environment variable.
`mcp_server.py` reads the listener's port and its rotating session credential
from Toolbelt's local handoff file each time it connects. Set `UEFN_MCP_PORT`
only to override the port, and only with the port the listener actually bound.

## 3. Check the registration

```bat
claude mcp get uefn-toolbelt
```

```bat
codex mcp get uefn-toolbelt
```

Each should show the command and arguments you registered. Claude Code also
shows `Connected` once the server starts. Neither check contacts UEFN.

## 4. Use it

1. Open UEFN and your project, then start the listener in the UEFN Python
   console (or **Dashboard → MCP → Start Listener**):
   ```python
   import UEFN_Toolbelt as tb; tb.run("mcp_start")
   ```
   Start it again in each editor session.
2. Open a **new** chat in the client. A chat that was already open when you
   registered may not see the new tools; if a new chat still doesn't, restart
   the client app once.
3. Ask, for example: *"Ping the UEFN Toolbelt, then list the first page of
   actors in my level."*

Your client's normal approval prompts still apply to every Toolbelt call. A
registered server makes the tools available; it does not approve them. Keep
approvals on for tools that change the level, and save the level yourself when
you're happy with the result.

## If it doesn't connect

- **The tools don't appear in the chat:** open a new chat, then restart the
  client app. Check the registration with step 3.
- **`ping` fails with a connection error:** the listener isn't running, or UEFN
  restarted since you last started it. Run `mcp_start` again.
- **`mcp_start` reports only one loaded tool:** Epic's UEFN MCP Toolsets beta
  triggered Quirk #36. Run `tb.register()` once, then `mcp_start`. See
  `docs/UEFN_QUIRKS.md`.
- **The server fails to start:** the registered interpreter lacks `mcp`, or a
  path is wrong. Run the registered command yourself in a terminal to see the
  error.

## Remove or change it

```bat
claude mcp remove --scope user uefn-toolbelt
```

```bat
codex mcp remove uefn-toolbelt
```

Then register again with the new paths.

## Per-project alternative

To limit Toolbelt to one folder in Claude Code instead, copy
`.mcp.json.template` to a gitignored `.mcp.json` in that folder and set the
absolute path to `mcp_server.py` (README Step 8). Never commit `.mcp.json`.

## Large listings

`list_toolbelt_tools` and `get_all_actors` return one bounded page per call, so
replies stay within client output limits. The agent follows `next_offset` until
`complete` is true. See [Paged MCP tool listings](../.claude/mcp_reference.md#paged-mcp-tool-listings-mcp_serverpy).

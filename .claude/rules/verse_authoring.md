---
paths:
  - "**/*.verse"
  - ".claude/agents/verse-deployer.md"
---

# Verse Authoring Rules (active when editing .verse files)

## Class structure

```verse
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }

my_device<public> := class(creative_device):
    @editable MyDevice : some_device = some_device{}

    OnBegin<override>()<suspends> : void =
        # entry point
```

- Always subclass `creative_device`, not `class`
- `@editable` props declared at class level, before `OnBegin`
- `OnBegin<override>()<suspends> : void =` — exact signature required, no variations

## Syntax rules

- **Tab indentation only** — no spaces. Ever.
- **String concat**: `"Hello " + player_name` — no f-strings, no `{}`
- **No semicolons** — Verse does not use them
- **`var` for mutable**: `var Score : int = 0` then `set Score = Score + 1`
- **Async calls in `<suspends>` context only** — `Sleep(0.0)`, `Await`, etc.

## Common patterns

```verse
# Wait for event
loop:
    Player := await SomeDevice.ActivatedEvent
    HandlePlayer(Player)

# Delay
Sleep(3.0)

# Team check
if (Team := Player.GetFortCharacter[].GetTeam[]):
    # do team logic
```

## Error fix loop

1. Run `tb.run("verse_patch_errors")` — returns `errors_by_file` with `error_type` and `fix_hint` per error
2. Fix ALL errors in one pass before redeploying
3. Write fixed file with `tb.run("verse_write_file", filename=..., content=..., overwrite=True)`
4. Tell user to click **Verse → Build Verse Code** in UEFN
5. Run `tb.run("verse_build_status")` to confirm SUCCESS

## Do not

- Add imports or using directives that don't exist in the project
- Remove `@editable` declarations — they wire up editor-assigned devices
- Change `OnBegin` signature
- Use spaces for indentation

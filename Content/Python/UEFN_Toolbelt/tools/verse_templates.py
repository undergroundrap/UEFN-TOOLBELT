"""
UEFN TOOLBELT — verse_templates.py
====================================
Battle-tested Verse templates for common game patterns.
Claude assembles from these instead of hallucinating Verse syntax from scratch.

Each template is a confirmed-syntax starting point that compiles with one or
zero passes through verse_patch_errors.  Parameterisation is intentionally
minimal — device names are left as readable labels so Claude can fill them
from world_state_export actor labels without risk of wrong API names.

Workflow:
  1. tb.run("world_state_export")          # see what devices are in the level
  2. tb.run("verse_template_list")         # pick a template
  3. tb.run("verse_template_get", name=X)  # read source + devices_needed
  4. Claude fills device labels, renames class, adjusts constants
  5. tb.run("verse_template_deploy", name=X, filename="game.verse")
  6. User clicks Build Verse
  7. tb.run("verse_patch_errors")          # fix any API name mismatches
"""

import unreal
import os
from ..registry import register_tool
from ..core import log_info, log_error

# ─────────────────────────────────────────────────────────────────────────────
#  Template library
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES = {

    "game_skeleton": {
        "description": (
            "Full game manager device — round start/end, timer, scoreboard, spawn pads. "
            "Starting point for any game mode. Rename the class and wire devices."
        ),
        "devices_needed": [
            "player_spawner_device (x2) — SpawnPad1, SpawnPad2",
            "scoreboard_device — Scoreboard",
            "timer_device — EndGameTimer",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Fortnite.com/Game }
using { /Fortnite.com/Teams }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# ──────────────────────────────────────────────────────────────
# game_manager
# Main game manager — attach to a Creative Device Blueprint.
# STEP 1: Rename 'game_manager' to match your Blueprint class.
# STEP 2: Wire @editable fields to level devices in Details panel.
# STEP 3: Click Build Verse. Run verse_patch_errors if errors.
# ──────────────────────────────────────────────────────────────
game_manager := class(creative_device):

    @editable SpawnPad1    : player_spawner_device = player_spawner_device{}
    @editable SpawnPad2    : player_spawner_device = player_spawner_device{}
    @editable Scoreboard   : scoreboard_device     = scoreboard_device{}
    @editable EndGameTimer : timer_device          = timer_device{}

    @editable MaxScore     : int   = 10
    @editable RoundTimeSec : float = 300.0

    var CurrentScore<private> : int = 0

    OnBegin<override>()<suspends> : void =
        Print("game_manager: OnBegin")
        _SetupEvents()
        _StartRound()

    _SetupEvents<private>() : void =
        EndGameTimer.SuccessEvent.Subscribe(OnTimerExpired)

    _StartRound<private>()<suspends> : void =
        set CurrentScore = 0
        SpawnPad1.Enable()
        SpawnPad2.Enable()
        EndGameTimer.Start()
        Print("game_manager: Round started")

    OnTimerExpired<private>(TimerDevice : timer_device) : void =
        Print("game_manager: Timer expired")
        _EndRound()

    _EndRound<private>() : void =
        SpawnPad1.Disable()
        SpawnPad2.Disable()
        EndGameTimer.Stop()
        Scoreboard.ShowScoreboard()
""",
    },

    "elimination_scoring": {
        "description": (
            "Award points for eliminations. First to ScoreToWin wins. "
            "Wire Scoreboard and EndGame. Subscribe EliminationEvent from your "
            "elimination_manager_device in OnBegin."
        ),
        "devices_needed": [
            "scoreboard_device — Scoreboard",
            "end_game_device — EndGame",
            "elimination_manager_device — subscribe EliminationEvent in OnBegin",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# elimination_scoring
# Players earn points per kill. First to ScoreToWin activates EndGame.
# STEP 1: Wire Scoreboard and EndGame in Details panel.
# STEP 2: In OnBegin add: YourEliminationDevice.EliminationEvent.Subscribe(OnElimination)
elimination_scoring := class(creative_device):

    @editable Scoreboard   : scoreboard_device = scoreboard_device{}
    @editable EndGame      : end_game_device   = end_game_device{}

    @editable ScoreToWin   : int = 10
    @editable ScorePerKill : int = 1

    var PlayerScores<private> : [player]int = map{}

    OnBegin<override>()<suspends> : void =
        Print("elimination_scoring: ready, win at {ScoreToWin} kills")
        # TODO: subscribe your elimination device here:
        # YourEliminationDevice.EliminationEvent.Subscribe(OnElimination)

    OnElimination<private>(Result : elimination_result) : void =
        EliminatorAgent := Result.EliminatingAgent
        if (P := player[EliminatorAgent]):
            Current  := if (S := PlayerScores[P]) then S else 0
            NewScore := Current + ScorePerKill
            set PlayerScores[P] = NewScore
            Scoreboard.SetScoreboardScore(P, NewScore)
            if (NewScore >= ScoreToWin):
                EndGame.Activate(P)
                Print("elimination_scoring: winner at score {NewScore}")
""",
    },

    "zone_capture": {
        "description": (
            "Score points while players occupy a capture zone. "
            "Wire CaptureZone (mutator_zone_device), Scoreboard, EndGame."
        ),
        "devices_needed": [
            "mutator_zone_device — CaptureZone",
            "scoreboard_device — Scoreboard",
            "end_game_device — EndGame",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# zone_capture
# Each time a player enters the zone they score PointsPerEnter.
# First to ScoreToWin wins.
# STEP 1: Wire CaptureZone, Scoreboard, EndGame in Details panel.
zone_capture := class(creative_device):

    @editable CaptureZone    : mutator_zone_device = mutator_zone_device{}
    @editable Scoreboard     : scoreboard_device   = scoreboard_device{}
    @editable EndGame        : end_game_device     = end_game_device{}

    @editable PointsPerEnter : int = 1
    @editable ScoreToWin     : int = 20

    var PlayerScores<private> : [player]int = map{}

    OnBegin<override>()<suspends> : void =
        CaptureZone.AgentEntersZoneEvent.Subscribe(OnAgentEnter)
        Print("zone_capture: active, {ScoreToWin} points to win")

    OnAgentEnter<private>(Agent : agent) : void =
        if (P := player[Agent]):
            Current  := if (S := PlayerScores[P]) then S else 0
            NewScore := Current + PointsPerEnter
            set PlayerScores[P] = NewScore
            Scoreboard.SetScoreboardScore(P, NewScore)
            if (NewScore >= ScoreToWin):
                EndGame.Activate(P)
                Print("zone_capture: winner at score {NewScore}")
""",
    },

    "round_flow": {
        "description": (
            "Multi-round game. Runs RoundCount rounds, shows scoreboard between each, "
            "then ends. Wire SpawnPad, RoundTimer, Scoreboard."
        ),
        "devices_needed": [
            "player_spawner_device — SpawnPad",
            "timer_device — RoundTimer",
            "scoreboard_device — Scoreboard",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# round_flow
# Runs RoundCount rounds. Scoreboard shown between each round.
# STEP 1: Wire SpawnPad, RoundTimer, Scoreboard in Details panel.
# STEP 2: Set RoundCount and RoundDurationSec.
round_flow := class(creative_device):

    @editable SpawnPad         : player_spawner_device = player_spawner_device{}
    @editable RoundTimer       : timer_device          = timer_device{}
    @editable Scoreboard       : scoreboard_device     = scoreboard_device{}

    @editable RoundCount       : int   = 3
    @editable RoundDurationSec : float = 120.0

    var CurrentRound<private> : int = 0

    OnBegin<override>()<suspends> : void =
        RoundTimer.SuccessEvent.Subscribe(OnRoundEnd)
        Print("round_flow: {RoundCount}-round game starting")
        _StartNextRound()

    _StartNextRound<private>()<suspends> : void =
        set CurrentRound += 1
        if (CurrentRound > RoundCount):
            _EndGame()
        else:
            Print("round_flow: Round {CurrentRound} of {RoundCount}")
            SpawnPad.Enable()
            RoundTimer.Start()

    OnRoundEnd<private>(TimerDevice : timer_device) : void =
        Print("round_flow: Round {CurrentRound} ended")
        SpawnPad.Disable()
        RoundTimer.Stop()
        Scoreboard.ShowScoreboard()
        _StartNextRound()

    _EndGame<private>() : void =
        Print("round_flow: All {RoundCount} rounds complete")
        Scoreboard.ShowScoreboard()
""",
    },

    "item_spawner_cycle": {
        "description": (
            "Activates an item spawner on a trigger, then cycles it at RespawnIntervalSec. "
            "Set TotalCycles=0 for infinite."
        ),
        "devices_needed": [
            "item_spawner_device — ItemSpawner",
            "trigger_device — StartTrigger",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# item_spawner_cycle
# Trigger activates the spawner. Items cycle every RespawnIntervalSec.
# TotalCycles=0 means infinite cycling.
# STEP 1: Wire ItemSpawner and StartTrigger in Details panel.
item_spawner_cycle := class(creative_device):

    @editable ItemSpawner        : item_spawner_device = item_spawner_device{}
    @editable StartTrigger       : trigger_device      = trigger_device{}

    @editable RespawnIntervalSec : float = 30.0
    @editable TotalCycles        : int   = 0

    var CycleCount<private> : int = 0

    OnBegin<override>()<suspends> : void =
        StartTrigger.TriggeredEvent.Subscribe(OnStart)
        Print("item_spawner_cycle: ready, interval={RespawnIntervalSec}s")

    OnStart<private>(Agent : ?agent) : void =
        ItemSpawner.Enable()
        Print("item_spawner_cycle: started")
        loop:
            Sleep(RespawnIntervalSec)
            set CycleCount += 1
            if (TotalCycles > 0 and CycleCount >= TotalCycles):
                ItemSpawner.Disable()
                break
            ItemSpawner.Disable()
            Sleep(0.5)
            ItemSpawner.Enable()
            Print("item_spawner_cycle: cycle {CycleCount}")
""",
    },

    "countdown_race": {
        "description": (
            "Race to hit a trigger before the timer expires. "
            "First player to trigger WinTrigger wins. Handles timer expiry as draw."
        ),
        "devices_needed": [
            "trigger_device — WinTrigger",
            "timer_device — CountdownTimer",
            "end_game_device — EndGame",
            "player_spawner_device — SpawnPad",
        ],
        "verse": """\
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# countdown_race
# Race to activate WinTrigger before CountdownTimer runs out.
# STEP 1: Wire all four devices in Details panel.
# STEP 2: Set timer duration via the timer_device Details panel.
countdown_race := class(creative_device):

    @editable WinTrigger     : trigger_device       = trigger_device{}
    @editable CountdownTimer : timer_device          = timer_device{}
    @editable EndGame        : end_game_device       = end_game_device{}
    @editable SpawnPad       : player_spawner_device = player_spawner_device{}

    var GameOver<private> : logic = false

    OnBegin<override>()<suspends> : void =
        WinTrigger.TriggeredEvent.Subscribe(OnWinTriggered)
        CountdownTimer.FailureEvent.Subscribe(OnTimeUp)
        SpawnPad.Enable()
        CountdownTimer.Start()
        Print("countdown_race: GO!")

    OnWinTriggered<private>(Agent : ?agent) : void =
        if (not GameOver):
            set GameOver = true
            CountdownTimer.Stop()
            if (A := Agent?):
                if (P := player[A]):
                    EndGame.Activate(P)
                    Print("countdown_race: winner!")

    OnTimeUp<private>(TimerDevice : timer_device) : void =
        if (not GameOver):
            set GameOver = true
            SpawnPad.Disable()
            Print("countdown_race: time's up, no winner")
""",
    },

}


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    name="verse_template_list",
    category="Verse Helpers",
    description=(
        "List all available Verse game templates — battle-tested patterns Claude "
        "assembles from instead of generating Verse syntax from scratch. "
        "Returns name, description, and required devices for each template."
    ),
    tags=["verse", "template", "list", "ai", "automation", "game", "pattern"],
    example='tb.run("verse_template_list")',
)
def verse_template_list(**kwargs) -> dict:
    """
    Return a catalogue of all available Verse templates with descriptions
    and required device lists.  Claude reads this first to pick the right
    template for the game mode it is building.

    Returns:
        {
          "status": "ok",
          "count":  int,
          "templates": {
            "game_skeleton":        {"description": ..., "devices_needed": [...]},
            "elimination_scoring":  {...},
            ...
          }
        }
    """
    catalogue = {
        name: {
            "description":   t["description"],
            "devices_needed": t["devices_needed"],
        }
        for name, t in _TEMPLATES.items()
    }
    log_info(f"verse_template_list: {len(_TEMPLATES)} templates available")
    return {
        "status":    "ok",
        "count":     len(_TEMPLATES),
        "templates": catalogue,
        "tip": (
            "Call verse_template_get(name=X) to read full source. "
            "Call verse_template_deploy(name=X, filename=Y) to write to the Verse source dir."
        ),
    }


@register_tool(
    name="verse_template_get",
    category="Verse Helpers",
    description=(
        "Return the full Verse source for a named template. "
        "Claude reads this, fills device labels from world_state_export, "
        "then deploys with verse_template_deploy or verse_write_file."
    ),
    tags=["verse", "template", "get", "source", "ai", "automation", "game"],
    example='tb.run("verse_template_get", name="elimination_scoring")',
)
def verse_template_get(name: str = "", **kwargs) -> dict:
    """
    Return the full Verse source of a named template.

    Args:
        name: Template name from verse_template_list (e.g. "elimination_scoring")

    Returns:
        {
          "status":         "ok",
          "name":           str,
          "description":    str,
          "devices_needed": [str, ...],
          "verse":          str,   # full Verse source ready to edit and deploy
          "next_step":      str    # plain-English instruction for Claude
        }
    """
    if not name:
        return {
            "status": "error",
            "error":  "name is required. Call verse_template_list to see available templates.",
        }
    if name not in _TEMPLATES:
        return {
            "status":    "error",
            "error":     f"Template '{name}' not found.",
            "available": list(_TEMPLATES.keys()),
        }
    t = _TEMPLATES[name]
    log_info(f"verse_template_get: returning '{name}'")
    return {
        "status":         "ok",
        "name":           name,
        "description":    t["description"],
        "devices_needed": t["devices_needed"],
        "verse":          t["verse"],
        "next_step": (
            f"1. Read 'verse' source above.\n"
            f"2. Replace device names with actual actor labels from world_state_export.\n"
            f"3. Adjust @editable constants for your game mode.\n"
            f"4. Call verse_template_deploy(name='{name}', filename='your_file.verse') or "
            f"verse_write_file(filename='your_file.verse', content=<edited_source>, overwrite=True).\n"
            f"5. User clicks Build Verse.\n"
            f"6. Call verse_patch_errors() to fix any issues."
        ),
    }


@register_tool(
    name="verse_template_deploy",
    category="Verse Helpers",
    description=(
        "Write a Verse template directly into the project's Verse source directory. "
        "Shortcut for verse_template_get + verse_write_file in one call. "
        "Pass custom_source to override the template source before writing."
    ),
    tags=["verse", "template", "deploy", "write", "ai", "automation"],
    example='tb.run("verse_template_deploy", name="zone_capture", filename="zone_game.verse")',
)
def verse_template_deploy(
    name: str = "",
    filename: str = "",
    custom_source: str = "",
    overwrite: bool = False,
    **kwargs,
) -> dict:
    """
    Write a template (or custom_source override) to the Verse source directory.

    Args:
        name:          Template name from verse_template_list
        filename:      Output .verse filename (e.g. "zone_game.verse")
        custom_source: If provided, write this instead of the raw template source.
                       Use this when Claude has edited the template for the level.
        overwrite:     Overwrite if file already exists (default False)

    Returns:
        verse_write_file result dict + template metadata
    """
    if not name:
        return {"status": "error", "error": "name is required."}
    if name not in _TEMPLATES:
        return {
            "status":    "error",
            "error":     f"Template '{name}' not found.",
            "available": list(_TEMPLATES.keys()),
        }

    source = custom_source if custom_source else _TEMPLATES[name]["verse"]
    out_filename = filename or f"{name}.verse"

    # Delegate to verse_write_file
    try:
        import UEFN_Toolbelt as tb
        result = tb.run("verse_write_file", filename=out_filename, content=source, overwrite=overwrite)
        if result and result.get("status") == "ok":
            log_info(f"verse_template_deploy: '{name}' deployed as '{out_filename}'")
            result["template"] = name
            result["devices_needed"] = _TEMPLATES[name]["devices_needed"]
            result["next_step"] = (
                f"File written. Now:\n"
                f"1. Open UEFN and wire the @editable devices in the Details panel.\n"
                f"2. Click Build Verse.\n"
                f"3. Call tb.run('verse_patch_errors') to check for errors."
            )
        return result or {"status": "error", "error": "verse_write_file returned None"}
    except Exception as e:
        log_error(f"verse_template_deploy failed: {e}")
        return {"status": "error", "error": str(e)}

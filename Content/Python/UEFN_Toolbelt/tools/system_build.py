import os
import subprocess
import re
import unreal
from ..registry import register_tool
from ..core import log_info, log_error, log_warning, with_progress

class VerseBuildService:
    @staticmethod
    def find_uefn_cmd():
        """Attempts to find the UnrealEditor-Cmd.exe globally or in project-relative folders."""
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        possible_paths = [
            # Common installation paths
            os.path.join(program_files, "Epic Games", "Fortnite", "FortniteGame", "Binaries", "Win64", "UnrealEditor-Cmd.exe"),
            os.path.join(program_files, "Epic Games", "Fortnite", "Engine", "Binaries", "Win64", "UnrealEditor-Cmd.exe")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def trigger_build():
        """Runs the UEFN command-line build specifically for Verse."""
        uefn_exe = VerseBuildService.find_uefn_cmd()
        if not uefn_exe:
            return None, "Error: UEFN (UnrealEditor-Cmd.exe) not found. Please set the path manually."
            
        project_file = unreal.Paths.get_project_file_path()
        if not project_file or not os.path.exists(project_file):
            return None, "Error: No active .uproject file found."
            
        # Command line arguments for Verse compilation
        # -run=VerseBuilder is a common UEFN pattern
        args = [
            uefn_exe,
            project_file,
            "-run=VerseBuilder",
            "-noshadercompile",
            "-silent",
            "-stdout"
        ]
        
        try:
            log_info(f"Triggering Verse Build: {os.path.basename(project_file)}")
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.stdout + "\n" + result.stderr, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def parse_verse_errors(output):
        """Regex-based extraction of Verse errors from build output."""
        errors = []
        # Pattern: filepath(line:col): error message
        pattern = re.compile(r'(.+\.verse)\((\d+)(?::(\d+))?\)\s*:\s*(?:error\s*)?(.+)', re.IGNORECASE)
        
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                errors.append({
                    "file": match.group(1).strip(),
                    "line": int(match.group(2)),
                    "column": int(match.group(3)) if match.group(3) else None,
                    "message": match.group(4).strip()
                })
        return errors

@register_tool(name="system_build_verse", category="System")
def system_build_verse(**kwargs) -> dict:
    """
    Triggers a background UEFN build to compile Verse and return errors.
    This replaces the manual 'Push Changes' loop for rapid AI diagnostics.
    """
    with with_progress("Compiling Verse...") as progress:
        output, err = VerseBuildService.trigger_build()
        if err:
            log_error(err)
            return {"status": "error", "message": err}
            
        errors = VerseBuildService.parse_verse_errors(output)
        
        if errors:
            log_warning(f"Build failed with {len(errors)} Verse errors.")
            return {
                "status": "failed",
                "count": len(errors),
                "errors": errors
            }
        
        log_info("Verse Build Successful.")
        return {"status": "success", "message": "Verse compiled with 0 errors."}

@register_tool(name="system_get_last_build_log", category="System")
def system_get_last_build_log(**kwargs) -> dict:
    """Reads the most recent UEFN log file for error analysis."""
    log_dir = os.path.join(unreal.Paths.project_saved_dir(), "Logs")
    if not os.path.exists(log_dir):
        return {"status": "error", "path": None, "tail": "Log directory not found."}

    logs = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")]
    if not logs:
        return {"status": "error", "path": None, "tail": "No log files found."}

    latest_log = max(logs, key=os.path.getmtime)
    with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().splitlines()

    return {"status": "ok", "path": latest_log, "tail": "\n".join(content[-100:])}


def _find_verse_root() -> str:
    """Walk up from __file__ to find the UEFN project root, return its Verse directory."""
    curr = os.path.abspath(__file__)
    while True:
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        if os.path.basename(curr) == "Content":
            verse_dir = os.path.join(parent, "Verse")
            return verse_dir if os.path.isdir(verse_dir) else parent
        curr = parent
    return ""


@register_tool(
    name="verse_patch_errors",
    category="System",
    description=(
        "The AI error loop tool. After a failed Verse build, reads the log, "
        "extracts every error with file/line/message, and returns the full content "
        "of each erroring file -- so Claude can fix and redeploy in one shot."
    ),
    tags=["verse", "build", "error", "patch", "fix", "loop", "ai", "automation", "recursive"],
)
def verse_patch_errors(verse_file: str = "", **kwargs) -> dict:
    """
    Closes the AI build loop. Call this immediately after a Verse build failure.

    What it does:
      1. Finds the most recent UEFN log file
      2. Scans it for Verse error lines (file.verse(line:col): error message)
      3. Also scans for VerseBuild summary lines (ERROR / WARNING counts)
      4. For each erroring .verse file, reads its full content from disk
      5. Returns everything in one structured dict

    Claude's complete fix workflow:
      +-------------------------------------------------------------+
      |  1. User clicks Build Verse -> errors appear                |
      |  2. tb.run("verse_patch_errors")                            |
      |     -> errors: [{file, line, col, message}, ...]            |
      |     -> files:  {"game_manager.verse": "...content..."}      |
      |  3. Claude reads errors + file content                      |
      |  4. Claude generates fixed_content                          |
      |  5. tb.run("verse_write_file",                              |
      |            filename="game_manager.verse",                   |
      |            content=fixed_content, overwrite=True)           |
      |  6. User clicks Build Verse again                           |
      |  7. REPEAT until: build_status == "SUCCESS"                 |
      +-------------------------------------------------------------+

    Args:
        verse_file: Optional. If set, always include this filename's content
                    even if it has no errors (useful for context).

    Returns:
        {
          "status":       "errors" | "success" | "no_log" | "error",
          "build_status": "SUCCESS" | "FAILED" | "UNKNOWN",
          "error_count":  int,
          "warning_count": int,
          "errors": [
            {
              "file":    "game_manager.verse",
              "line":    42,
              "col":     7,          # None if not present
              "message": "identifier 'capture_area_device' not found"
            }
          ],
          "files": {
            "game_manager.verse": "...full file content..."
          },
          "log_path": str,
          "next_step": str          # plain-English instruction for Claude
        }

    Example:
        tb.run("verse_patch_errors")
        # If errors -> Claude reads result["errors"] + result["files"],
        #             generates fix, calls verse_write_file(overwrite=True)
        # If success -> result["build_status"] == "SUCCESS", nothing to fix
    """
    # -- 1. Find latest log --------------------------------------------------
    log_dir = os.path.join(unreal.Paths.project_saved_dir(), "Logs")
    if not os.path.exists(log_dir):
        return {"status": "no_log", "message": "Log directory not found.",
                "errors": [], "files": {}, "build_status": "UNKNOWN"}

    log_files = [os.path.join(log_dir, f)
                 for f in os.listdir(log_dir) if f.endswith(".log")]
    if not log_files:
        return {"status": "no_log", "message": "No log files found.",
                "errors": [], "files": {}, "build_status": "UNKNOWN"}

    latest_log = max(log_files, key=os.path.getmtime)

    with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
        log_lines = f.readlines()

    # -- 2. Parse errors and build status ------------------------------------
    # Error pattern: path/file.verse(line:col): error <message>
    # Also matches: path/file.verse(line): error <message>
    error_pattern = re.compile(
        r'([^\s]+\.verse)\((\d+)(?::(\d+))?\)\s*:.*?(?:error\s+)?(.+)',
        re.IGNORECASE
    )
    # Build status patterns -- covers both Output Log format and .log file format:
    #   Output Log:  "VerseBuild: SUCCESS -- Build complete."
    #   .log file:   "LogSolLoadCompiler: ... finished: SUCCESS."
    #   .log file:   "LogSolaris: ... VerseBuild SUCCESS"
    success_pattern = re.compile(
        r'(VerseBuild.*SUCCESS|LogSolLoadCompiler.*finished.*SUCCESS|LogSolaris.*VerseBuild.*SUCCESS)',
        re.IGNORECASE
    )
    failed_pattern = re.compile(
        r'(VerseBuild.*(?:FAIL|ERROR)|LogSolLoadCompiler.*finished.*(?:FAIL|ERROR))',
        re.IGNORECASE
    )
    # LogSolaris error lines (another common pattern)
    solaris_error   = re.compile(r'LogSolaris.*Error.*\.verse', re.IGNORECASE)

    errors = []
    build_status = "UNKNOWN"
    warning_count = 0

    for line in log_lines:
        if success_pattern.search(line):
            build_status = "SUCCESS"
        elif failed_pattern.search(line):
            if build_status != "SUCCESS":
                build_status = "FAILED"

        m = error_pattern.search(line)
        if m:
            file_path = m.group(1).strip()
            filename  = os.path.basename(file_path)
            line_no   = int(m.group(2))
            col_no    = int(m.group(3)) if m.group(3) else None
            message   = m.group(4).strip()

            # Skip duplicates (same file+line+message)
            key = (filename, line_no, message[:60])
            if not any(
                e["file"] == filename and e["line"] == line_no
                and e["message"][:60] == message[:60]
                for e in errors
            ):
                errors.append({
                    "file":    filename,
                    "line":    line_no,
                    "col":     col_no,
                    "message": message,
                    "raw_path": file_path,
                })

        if "warning" in line.lower() and ".verse" in line.lower():
            warning_count += 1

    # -- 3. Read erroring file contents --------------------------------------
    verse_root = _find_verse_root()
    files_out: dict = {}

    # Collect unique filenames from errors + optional explicit file
    target_files = {e["file"] for e in errors}
    if verse_file:
        target_files.add(verse_file if verse_file.endswith(".verse")
                         else verse_file + ".verse")

    for fname in target_files:
        # Search in verse root first, then walk subdirs
        found = False
        if verse_root and os.path.isdir(verse_root):
            for root, _, fnames in os.walk(verse_root):
                if fname in fnames:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            files_out[fname] = f.read()
                        found = True
                        break
                    except Exception:
                        pass

        if not found:
            # Try raw_path from the log
            for e in errors:
                if e["file"] == fname and os.path.isfile(e.get("raw_path", "")):
                    try:
                        with open(e["raw_path"], "r", encoding="utf-8") as f:
                            files_out[fname] = f.read()
                        break
                    except Exception:
                        pass

    # -- 4. Build response ---------------------------------------------------
    if build_status == "SUCCESS":
        next_step = "Build succeeded -- no errors to fix. Run world_state_export to verify the level."
    elif errors:
        next_step = (
            f"Fix {len(errors)} error(s) in the files listed under 'files', "
            f"then call verse_write_file(overwrite=True) and rebuild."
        )
    else:
        next_step = (
            "No structured errors parsed -- check the raw log via "
            "system_get_last_build_log for context."
        )

    log_info(f"[verse_patch_errors] build={build_status}  "
             f"errors={len(errors)}  warnings={warning_count}  "
             f"files_read={len(files_out)}")

    return {
        "status":        "success" if build_status == "SUCCESS" else
                         ("errors" if errors else "unknown"),
        "build_status":  build_status,
        "error_count":   len(errors),
        "warning_count": warning_count,
        "errors":        errors,
        "files":         files_out,
        "log_path":      latest_log,
        "next_step":     next_step,
    }

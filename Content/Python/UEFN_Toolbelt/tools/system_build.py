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
def system_build_verse():
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
def system_get_last_build_log() -> dict:
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

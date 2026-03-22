import unreal
import os
import zipfile
import datetime
from ..registry import register_tool
from ..core import log_info, log_error

@register_tool(
    name="system_backup_project",
    category="Project Admin",
    description="Creates a timestamped .zip backup of the Content folder.",
    tags=["system", "backup", "save", "admin", "archive"]
)
def run_system_backup_project(**kwargs):
    """
    Zips the Content folder into Saved/UEFN_Toolbelt/backups/
    """
    # Get project root (parent of Content)
    content_dir = unreal.Paths.project_content_dir()
    # Handle the fact that project_content_dir may be relative or have specific format
    # Convert to absolute OS path
    abs_content = os.path.abspath(content_dir)
    project_root = os.path.dirname(abs_content)
    
    backup_root = os.path.join(unreal.Paths.project_saved_dir(), "UEFN_Toolbelt", "backups")
    if not os.path.exists(backup_root):
        os.makedirs(backup_root)
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"Project_Backup_{timestamp}.zip"
    zip_path = os.path.join(backup_root, zip_name)
    
    log_info(f"Creating backup: {zip_name}...")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(abs_content):
                for file in files:
                    # Ignore massive build/temp files if any
                    if ".uasset" in file or ".umap" in file or ".verse" in file:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, project_root)
                        zipf.write(file_path, rel_path)
        
        size_mb = os.path.getsize(zip_path) / (1024 * 1024)
        log_info(f"✓ Backup complete: {zip_path} ({size_mb:.2f} MB)")
    except Exception as e:
        log_error(f"Backup failed: {str(e)}")

@register_tool(
    name="system_perf_audit",
    category="Project Admin",
    description="Fast performance check of the current level.",
    tags=["system", "performance", "audit", "memory"]
)
def run_system_perf_audit(**kwargs):
    """
    Prints a high-level performance snapshot.
    """
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_sub.get_all_level_actors()
    
    log_info("════════════════════════════════════════════════════════════")
    log_info(f"  PERFORMANCE AUDIT: {unreal.EditorLevelLibrary.get_editor_world().get_name()}")
    log_info("════════════════════════════════════════════════════════════")
    log_info(f"Total Actors: {len(all_actors)}")
    
    class_counts = {}
    for actor in all_actors:
        cls_name = actor.get_class().get_name()
        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
        
    sorted_counts = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    
    log_info("Top 5 Actor Classes:")
    for name, count in sorted_counts[:5]:
        log_info(f"  • {name}: {count}")
        
    # Check for excessive lights
    light_count = sum(1 for a in all_actors if "Light" in a.get_class().get_name())
    if light_count > 50:
        log_info(f"⚠️ High Light Count: {light_count} (May impact shadowed performance)")
    else:
        log_info(f"✓ Light Count: {light_count}")

    # Check for high-poly candidates
    mesh_actors = [a for a in all_actors if isinstance(a, unreal.StaticMeshActor)]
    log_info(f"Static Mesh Actors: {len(mesh_actors)}")
    
    log_info("════════════════════════════════════════════════════════════")

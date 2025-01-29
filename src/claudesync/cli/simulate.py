import os
import click
import json
import logging
from pathlib import Path

from ..exceptions import ConfigurationError
from ..project_references_manager import ProjectReferencesManager

logger = logging.getLogger(__name__)

def format_size(size):
    """Convert size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def print_project_files(project_id: str, files: dict, project_root: Path = None, show_size: bool = True):
    """Print files from a project with optional size information.

    Args:
        project_id: Identifier of the project
        files: Dictionary of files with relative paths as keys
        project_root: Root path of the project for resolving absolute paths
        show_size: Whether to show file sizes
    """
    total_size = 0

    click.echo(f"\nFiles in project '{project_id}':")
    if not files:
        click.echo("  No files found")
        return 0

    for rel_path in sorted(files.keys()):
        if project_root:
            # Use project_root to get absolute path
            full_path = project_root / rel_path
        else:
            # Fallback to relative path if no root provided
            full_path = Path(rel_path)

        if show_size:
            try:
                size = os.path.getsize(full_path)
                total_size += size
                click.echo(f"  {rel_path} ({format_size(size)})")
            except OSError as e:
                logger.debug(f"Error getting size for {full_path}: {e}")
                click.echo(f"  {rel_path} (size unknown)")
        else:
            click.echo(f"  {rel_path}")

    if show_size:
        click.echo(f"\nTotal size: {format_size(total_size)}")
    return total_size

@click.command()
@click.option('--port', default=4201, help='Port to run the server on')
@click.option('--no-browser', is_flag=True, help='Do not open browser automatically')
@click.option('--list', 'list_files', is_flag=True, help='List files that will be synced')
@click.pass_obj
def simulate_push(config, port, no_browser, list_files):
    """Simulate the sync operation.

    By default, launches a visualization in the browser. Use --list to print files instead."""
    try:
        # Get active project
        active_project_path, active_project_id = config.get_active_project()
        if not active_project_path:
            raise ConfigurationError("No active project found. Please set an active project using 'project set'")

        if list_files:
            # List mode - print files that would be synced
            click.echo(f"Files that would be synced for project: {active_project_path}")

            # Initialize project references manager
            ref_manager = ProjectReferencesManager()

            try:
                files_by_project = ref_manager.get_all_project_files(active_project_path)
            except ConfigurationError as e:
                logger.error(f"Error getting project files: {e}")
                files_by_project = {}

            # Print files in list mode
            grand_total = 0

            # Get main project root
            main_root = Path(config.get_project_root())

            # Print main project files first
            if 'main' in files_by_project:
                main_total = print_project_files('main', files_by_project['main'], main_root)
                grand_total += main_total

            # Get referenced project paths
            referenced_projects = ref_manager.get_referenced_projects(active_project_path)

            # Print referenced project files
            for project_id, files in files_by_project.items():
                if project_id != 'main':
                    # Get the root path for this referenced project
                    ref_project_path = referenced_projects.get(project_id)
                    if ref_project_path:
                        ref_root = ref_project_path.parent.parent  # Navigate up from the .project.json file
                        ref_total = print_project_files(project_id, files, ref_root)
                        grand_total += ref_total
                    else:
                        # Fallback if reference path not found
                        ref_total = print_project_files(project_id, files)
                        grand_total += ref_total

            # Print grand total
            if grand_total > 0:
                click.echo(f"\nTotal size across all projects: {format_size(grand_total)}")

        else:
            # Default visualization mode
            web_dir = os.path.join(os.path.dirname(__file__), '../web/dist/claudesync-simulate')
            logger.debug(f"Web directory path: {web_dir}")

            if not os.path.exists(web_dir):
                logger.error(f"Web directory does not exist: {web_dir}")
                click.echo(f"Error: Web directory not found at {web_dir}")
                return

            click.echo(f"Simulating sync for project: {active_project_path}")

            # Start server and launch browser
            from .server_handler import start_simulation_server
            start_simulation_server(web_dir, port, no_browser, config)

    except ConfigurationError as e:
        click.echo(f"Error: {str(e)}")
        return

def get_file_stats(files_by_project):
    """Calculate statistics for files across all projects."""
    stats = {
        'total_files': 0,
        'total_size': 0,
        'projects': {}
    }

    for project_id, files in files_by_project.items():
        project_size = 0
        for file_path in files:
            try:
                size = os.path.getsize(file_path)
                project_size += size
                stats['total_size'] += size
                stats['total_files'] += 1
            except OSError:
                continue

        stats['projects'][project_id] = {
            'files': len(files),
            'size': project_size
        }

    return stats
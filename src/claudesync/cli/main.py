from pathlib import Path

import logging
import sys
import click
import click_completion
import click_completion.core
import json
import subprocess
import urllib.request
from pkg_resources import get_distribution

from ..cli.file import file
from ..cli.chat import chat

from ..project_references_manager import ProjectReferencesManager
from ..configmanager import FileConfigManager
from ..exceptions import ConfigurationError
from ..syncmanager import SyncManager
from ..utils import (
    handle_errors,
    validate_and_get_provider,
    get_local_files,
)
from .auth import auth
from .organization import organization
from .project import project
from .simulate import simulate_push
from .config import config
from .zip import zip
import logging

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

click_completion.init()


def setup_logging(config):
    """Configure logging based on the configuration."""
    # Get log level from config
    log_level_str = config.get("log_level", "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Clear any existing handlers
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Create console handler with formatting
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Configure claudesync logger
    logger = logging.getLogger('claudesync')
    logger.setLevel(log_level)

    # Debug message to confirm logging is working
    logger.debug("Logging configured with level: %s", log_level_str)

@click.group()
@click.pass_context
def cli(ctx):
    """ClaudeSync: Synchronize local files with AI projects."""
    if ctx.obj is None:
        ctx.obj = FileConfigManager()  # InMemoryConfigManager() for testing with mock

    # Setup logging early
    setup_logging(ctx.obj)

@cli.command()
@click.argument(
    "shell", required=False, type=click.Choice(["bash", "zsh", "fish", "powershell"])
)
def install_completion(shell):
    """Install completion for the specified shell."""
    if shell is None:
        shell = click_completion.get_auto_shell()
        click.echo("Shell is set to '%s'" % shell)
    click_completion.install(shell=shell)
    click.echo("Completion installed.")


@cli.command()
@click.argument("project", required=False)
@click.pass_obj
@handle_errors
def push(config, project):
    """Synchronize the project files with Claude.ai."""
    if not project:
        # Use the active project if no project specified
        active_project_path, active_project_id = config.get_active_project()
        if not active_project_path:
            raise ConfigurationError(
                "No active project found. Please specify a project or set an active one using 'project set'"
            )
        project = active_project_path

    # Get configurations
    files_config = config.get_files_config(project)
    project_root = Path(config.get_project_root())

    # Validate provider and get organization/project IDs
    provider = validate_and_get_provider(config)
    active_organization_id = config.get("active_organization_id")
    project_id = config.get_project_id(project)

    try:
        # Initialize referenced projects manager
        ref_manager = ProjectReferencesManager()

        # Get all files from main and referenced projects
        files_by_project = ref_manager.get_all_project_files(project)

        # Print summary of files to be synced
        total_files = sum(len(files) for files in files_by_project.values())
        click.echo(f"\nFound {total_files} files across all projects:")

        # Enhanced files collection with root paths
        all_files = {}
        referenced_projects = ref_manager.get_referenced_projects(project)

        # Process referenced project files first
        for pid, files in files_by_project.items():
            if pid != 'main':
                ref_path = referenced_projects.get(pid)
                if ref_path:
                    # Get the actual root directory for the referenced project
                    ref_root = ref_path.parent.parent  # Navigate up from .project.json
                    click.echo(f"  - {pid}: {len(files)} files")

                    # Add files with their root paths
                    for file_path, file_hash in files.items():
                        all_files[file_path] = {
                            'hash': file_hash,
                            'root_path': ref_root
                        }
                        logger.debug(f"Added referenced file {file_path} from {ref_root}")

        # Add main project files last (overriding any duplicates)
        if 'main' in files_by_project:
            main_files = files_by_project['main']
            click.echo(f"  - main: {len(main_files)} files")
            for file_path, file_hash in main_files.items():
                all_files[file_path] = {
                    'hash': file_hash,
                    'root_path': project_root
                }
                logger.debug(f"Added main project file {file_path}")

        # Get remote files
        remote_files = provider.list_files(active_organization_id, project_id)
        logger.debug(f"Found {len(remote_files)} files on remote")

        # Set as active project
        config.set_active_project(project, project_id)

        # Create sync manager
        sync_manager = SyncManager(provider, config, project_id, project_root)

        # Sync all files
        sync_manager.sync(all_files, remote_files)

        click.echo(f"\nProject '{project}' synced successfully:")
        click.echo(f"- Total files synced: {len(all_files)}")
        click.echo(f"- Remote URL: https://claude.ai/project/{project_id}")

    except Exception as e:
        click.echo(f"\nError syncing referenced projects: {str(e)}")
        click.echo("Falling back to syncing main project only...")

        try:
            # Fallback to syncing only main project
            local_files = get_local_files(config, project_root, files_config)
            remote_files = provider.list_files(active_organization_id, project_id)

            sync_manager = SyncManager(provider, config, project_id, project_root)
            sync_manager.sync(local_files, remote_files)

            click.echo(f"\nProject '{project}' synced successfully (main project only):")
            click.echo(f"- Total files synced: {len(local_files)}")
            click.echo(f"- Remote URL: https://claude.ai/project/{project_id}")

        except Exception as fallback_error:
            click.echo(f"\nError during fallback sync: {str(fallback_error)}")
            raise ConfigurationError("Failed to sync project files")

cli.add_command(auth)
cli.add_command(organization)
cli.add_command(project)
cli.add_command(config)
cli.add_command(chat)
cli.add_command(simulate_push)
cli.add_command(file)
cli.add_command(zip)

if __name__ == "__main__":
    cli()
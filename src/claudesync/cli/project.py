import json
from pathlib import Path
from typing import List, Optional, Dict

import click
import os
import logging

from tqdm import tqdm
from ..provider_factory import get_provider
from ..utils import handle_errors, validate_and_get_provider
from ..exceptions import ProviderError, ConfigurationError
from .file import file
from ..syncmanager import retry_on_403

logger = logging.getLogger(__name__)


@click.group()
def project():
    """Manage AI projects within the active organization."""
    pass

def get_default_internal_name():
    """
    Determine default internal name based on existing projects.
    Returns 'all' if no projects exist, None otherwise.
    """
    from claudesync.configmanager import FileConfigManager

    config = FileConfigManager()
    try:
        projects = config.get_projects()
        return 'all' if not projects else None
    except ConfigurationError:
        return 'all'  # Return 'all' if no .claudesync directory exists yet

@project.command()
@click.option("--template", help="Name of an existing project to use as a template (e.g. 'myproject' will use .claudesync/myproject.project.json)",)
@click.option("--name", help="The name of the project", required=False,)
@click.option("--internal-name",help="The internal name used for configuration files",required=False,)
@click.option("--description", help="The project description", required=False,)
@click.option("--organization", help="The organization ID to use for this project", required=False,)
@click.option("--no-git-check", is_flag=True, help="Skip git repository check",)
@click.option("--references", help="Comma-separated list of referenced project identifiers", required=False)
@click.option("--reference-paths", help="JSON string mapping reference IDs to paths", required=False)
@click.pass_context
@handle_errors
def create(ctx, template, name, internal_name, description, organization, no_git_check, references, reference_paths):
    """Creates a new project with optional referenced projects support."""
    config = ctx.obj
    provider_instance = get_provider(config)

    # Process template if provided
    template_config = None
    if template:
        template_config = _load_template_config(template)

    # Get project details either from template, options, or prompt
    name, internal_name, description = _get_project_details(
        name, internal_name, description, template_config
    )

    # Process references
    reference_ids = _process_references(references)
    reference_paths_dict = _process_reference_paths(reference_paths)

    # Validate reference paths if provided
    if reference_ids and reference_paths_dict:
        _validate_reference_configuration(reference_ids, reference_paths_dict)

    # Create project remotely
    new_project = _create_remote_project(
        provider_instance, organization, name, description
    )

    # Create local configuration files
    _create_local_configuration(
        config,
        new_project,
        name,
        internal_name,
        description,
        template_config,
        reference_ids,
        reference_paths_dict
    )

    click.echo(f"\nProject created successfully:")
    _display_project_info(new_project, internal_name, reference_ids)

def _load_template_config(template: str) -> Optional[dict]:
    """Load configuration from template project."""
    try:
        claudesync_dir = Path.cwd() / ".claudesync"
        template_file = claudesync_dir / f"{template}.project.json"

        if not template_file.exists():
            raise ConfigurationError(f"Template project configuration not found: {template_file}")

        with open(template_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in template file: {str(e)}")
    except IOError as e:
        raise ConfigurationError(f"Error reading template file: {str(e)}")

def _get_project_details(
        name: Optional[str],
        internal_name: Optional[str],
        description: Optional[str],
        template_config: Optional[dict]
) -> tuple:
    """Get project details from template, options, or prompt."""
    # Use template values if available
    if template_config:
        name = name or template_config.get('project_name')
        internal_name = internal_name or get_default_internal_name()
        description = description or template_config.get(
            'project_description', "Project created with ClaudeSync"
        )

    # Otherwise prompt for values
    if not name:
        name = click.prompt(
            "Enter a title for your new project",
            default=Path.cwd().name
        )

    if not internal_name:
        default_internal = get_default_internal_name()
        internal_name = click.prompt(
            "Enter the internal name for your project (used for config files)",
            default=default_internal
        )

    if not description:
        description = click.prompt(
            "Enter the project description",
            default="Project created with ClaudeSync"
        )

    return name, internal_name, description

def _process_references(references: Optional[str]) -> List[str]:
    """Process comma-separated references into list."""
    if not references:
        return []
    return [ref.strip() for ref in references.split(',') if ref.strip()]

def _process_reference_paths(reference_paths: Optional[str]) -> Dict[str, str]:
    """Process JSON reference paths string into dictionary."""
    if not reference_paths:
        return {}

    try:
        paths_dict = json.loads(reference_paths)
        if not isinstance(paths_dict, dict):
            raise ConfigurationError("Reference paths must be a JSON object")
        return paths_dict
    except json.JSONDecodeError:
        raise ConfigurationError("Invalid JSON in reference paths")

def _validate_reference_configuration(
        reference_ids: List[str],
        reference_paths: Dict[str, str]
) -> None:
    """Validate reference configuration."""
    # Check all referenced projects have paths
    missing_paths = [ref_id for ref_id in reference_ids if ref_id not in reference_paths]
    if missing_paths:
        raise ConfigurationError(
            f"Missing paths for referenced projects: {', '.join(missing_paths)}"
        )

    # Validate each reference path
    for ref_id, path in reference_paths.items():
        path_obj = Path(path)

        # Path must be absolute
        if not path_obj.is_absolute():
            raise ConfigurationError(f"Reference path must be absolute: {path}")

        # Path must exist and be readable
        if not path_obj.exists():
            raise ConfigurationError(f"Reference path does not exist: {path}")

        if not os.access(path, os.R_OK):
            raise ConfigurationError(f"Reference path is not readable: {path}")

        # Must be within a .claudesync directory
        if '.claudesync' not in path_obj.parts:
            raise ConfigurationError(
                f"Reference path must be within .claudesync directory: {path}"
            )

        # No symlinks allowed
        if path_obj.is_symlink():
            raise ConfigurationError(f"Symlinks not allowed in reference paths: {path}")

def _create_remote_project(provider_instance, organization, name, description) -> dict:
    """Create project on remote provider."""
    organizations = provider_instance.get_organizations()
    organization_instance = organizations[0] if organizations else None
    organization_id = organization or organization_instance["id"]

    new_project = provider_instance.create_project(organization_id, name, description)
    click.echo(
        f"Project '{new_project['name']}' (uuid: {new_project['uuid']}) "
        f"has been created successfully."
    )
    return new_project

def _create_local_configuration(
        config,
        new_project: dict,
        name: str,
        internal_name: str,
        description: str,
        template_config: Optional[dict],
        reference_ids: List[str],
        reference_paths: Dict[str, str]
) -> None:
    """Create local configuration files."""
    current_dir = Path.cwd()
    claudesync_dir = current_dir / ".claudesync"
    os.makedirs(claudesync_dir, exist_ok=True)

    # Create project ID configuration
    project_id_config = {
        "project_id": new_project["uuid"],
        "reference_paths": reference_paths
    }

    # Create project configuration
    if template_config:
        project_config = {
            "project_name": new_project["name"],
            "project_description": description,
            "includes": template_config.get('includes', []),
            "excludes": template_config.get('excludes', []),
            "use_ignore_files": template_config.get('use_ignore_files', True),
            "push_roots": template_config.get('push_roots', []),
            "references": reference_ids
        }
    else:
        project_config = {
            "project_name": new_project["name"],
            "project_description": description,
            "includes": ["*"],
            "excludes": [],
            "use_ignore_files": True,
            "push_roots": [],
            "references": reference_ids
        }

    # Handle nested project paths
    config_path = Path(internal_name)
    if len(config_path.parts) > 1:
        os.makedirs(claudesync_dir / config_path.parent, exist_ok=True)

    # Save configurations
    project_id_config_path = claudesync_dir / f"{internal_name}.project_id.json"
    with open(project_id_config_path, 'w') as f:
        json.dump(project_id_config, f, indent=2)

    project_config_path = claudesync_dir / f"{internal_name}.project.json"
    with open(project_config_path, 'w') as f:
        json.dump(project_config, f, indent=2)

    # Set as active project
    config.set_active_project(internal_name, new_project["uuid"])

def _display_project_info(new_project: dict, internal_name: str, reference_ids: List[str]) -> None:
    """Display project information after creation."""
    current_dir = Path.cwd()
    click.echo(f"Project location: {current_dir}")
    click.echo(f"Project ID config: {current_dir}/.claudesync/{internal_name}.project_id.json")
    click.echo(f"Project config: {current_dir}/.claudesync/{internal_name}.project.json")
    click.echo(f"Remote URL: https://claude.ai/project/{new_project['uuid']}")

    if reference_ids:
        click.echo("\nReferenced projects:")
        for ref_id in reference_ids:
            click.echo(f"  - {ref_id}")

# Add this to src/claudesync/cli/project.py, right after the @project.command() create function

@project.command()
@click.argument("project-path", required=True)
@click.pass_obj
@handle_errors
def set(config, project_path):
    """Set the active project.

    PROJECT_PATH: The project path like 'datamodel/typeconstraints' or 'myproject'"""
    try:
        # Get project ID from config
        project_id = config.get_project_id(project_path)

        # Set as active project
        config.set_active_project(project_path, project_id)

        # Get project details
        files_config = config.get_files_config(project_path)
        project_name = files_config.get('project_name', 'Unknown Project')

        click.echo(f"Set active project to '{project_name}'")
        click.echo(f"  - Project path: {project_path}")
        click.echo(f"  - Project ID: {project_id}")
        click.echo(f"  - Project location: {config.get_project_root()}")
        click.echo(f"  - Remote URL: https://claude.ai/project/{project_id}")

    except ConfigurationError as e:
        click.echo(f"Error: {str(e)}")
        click.echo("Make sure the project exists and has been properly configured.")
        click.echo("You may need to create the project first using 'claudesync project create'")

@project.command()
@click.pass_obj
@handle_errors
def archive(config):
    """Archive the active project."""
    try:
        # Get active project
        active_project_path, active_project_id = config.get_active_project()
        if not active_project_path:
            raise ConfigurationError("No active project found. Please set an active project using 'project set'")

        # Get project details
        files_config = config.get_files_config(active_project_path)
        project_name = files_config.get('project_name', 'Unknown Project')

        # Get provider and archive the project
        provider = validate_and_get_provider(config)
        active_organization_id = config.get("active_organization_id")
        provider.archive_project(active_organization_id, active_project_id)

        click.echo(f"Successfully archived project '{project_name}'")
        click.echo(f"  - Project path: {active_project_path}")
        click.echo(f"  - Project ID: {active_project_id}")

    except ConfigurationError as e:
        click.echo(f"Error: {str(e)}")
        click.echo("Make sure you have an active project set.")

@project.command()
@click.pass_obj
@handle_errors
def ls(config):
    """List all configured projects."""
    try:
        # Get all projects from config
        projects = config.get_projects()
        if not projects:
            click.echo("No projects found.")
            return

        # Get active project for comparison
        active_project_path, active_project_id = config.get_active_project()

        click.echo("\nConfigured projects:")
        for project_path, project_id in projects.items():
            # Get project details from project configuration
            try:
                files_config = config.get_files_config(project_path)
                project_name = files_config.get('project_name', 'Unknown Project')

                # Mark active project with an asterisk
                active_marker = "*" if project_path == active_project_path else " "

                click.echo(f"{active_marker} {project_name}")
                click.echo(f"  - Path: {project_path}")
                click.echo(f"  - ID: {project_id}")
                click.echo(f"  - URL: https://claude.ai/project/{project_id}")
                click.echo()

            except ConfigurationError:
                # Skip projects with missing or invalid configuration
                continue

        if active_project_path:
            click.echo("Note: Projects marked with * are currently active")

    except ConfigurationError as e:
        click.echo(f"Error: {str(e)}")

project.add_command(file)

__all__ = ["project"]

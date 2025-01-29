import json
import os
import hashlib
import time as time_module
from functools import wraps
from pathlib import Path
from typing import Dict, Optional, Union

import click
import pathspec
import logging

from .exceptions import ConfigurationError, ProviderError
from .provider_factory import get_provider

logger = logging.getLogger(__name__)

def get_local_files(project_config: dict, root_path: Union[str, Path], files_config: dict) -> Dict[str, str]:
    """
    Get local files matching the patterns in files configuration.

    Args:
        project_config (dict): Project configuration containing reference settings
        root_path (str | Path): Root path of the project
        files_config (dict): File patterns configuration containing includes/excludes

    Returns:
        Dict[str, str]: Dictionary mapping file paths to their hashes
    """
    # Ensure root_path is a string
    root_path = str(root_path)

    logger.debug(f"Starting get_local_files for root_path: {root_path}")
    logger.debug(f"Files configuration: {json.dumps(files_config, indent=2)}")

    use_ignore_files = files_config.get("use_ignore_files", True)
    gitignore = load_gitignore(root_path) if use_ignore_files else None
    claudeignore = load_claudeignore(root_path) if use_ignore_files else None

    # Get patterns from configuration
    includes = files_config.get("includes", ["*"])
    excludes = files_config.get("excludes", [])
    push_roots = files_config.get("push_roots", [])

    logger.debug(f"Include patterns: {includes}")
    logger.debug(f"Exclude patterns: {excludes}")
    logger.debug(f"Push roots: {push_roots}")

    category_excludes = None
    if excludes:
        category_excludes = pathspec.PathSpec.from_lines("gitwildmatch", excludes)

    files = {}

    # Log some path debugging information
    logger.debug(f"Root path exists: {os.path.exists(root_path)}")
    if push_roots:
        for push_root in push_roots:
            full_push_root = os.path.join(root_path, push_root)
            logger.debug(f"Push root path {full_push_root} exists: {os.path.exists(full_push_root)}")

    # Create pathspec for matching
    spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)
    logger.debug(f"Created pathspec from includes: {spec.patterns}")

    # Check base paths for include patterns
    for pattern in includes:
        base_path = os.path.join(root_path, pattern.split('*')[0].rstrip('/'))
        logger.debug(f"Checking base path for pattern {pattern}: {base_path}")
        logger.debug(f"Base path exists: {os.path.exists(base_path)}")
        if os.path.exists(base_path):
            logger.debug(f"Content of {base_path}: {os.listdir(os.path.dirname(base_path))}")
    exclude_dirs = {".git", ".svn", ".hg", ".bzr", "_darcs", "CVS", "claude_chats", ".claudesync"}

    # Get push_roots from configuration
    push_roots = files_config.get("push_roots", [])
    includes = files_config.get("includes", ["*"])
    excludes = files_config.get("excludes", [])

    category_excludes = None
    if excludes:
        category_excludes = pathspec.PathSpec.from_lines("gitwildmatch", excludes)

    spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)

    logger.debug(f"Starting file system traversal at {root_path}")
    logger.debug(f"Using ignore files: {use_ignore_files}")
    logger.debug(f"Using push roots: {push_roots}")
    traversal_start = time_module.time()

    # If push_roots is specified, only traverse those directories
    roots_to_traverse = [os.path.join(root_path, root) for root in push_roots] if push_roots else [root_path]

    for base_root in roots_to_traverse:
        if not os.path.exists(base_root):
            logger.warning(f"Specified root path does not exist: {base_root}")
            continue

        for root, dirs, filenames in os.walk(base_root, topdown=True):
            # Filter out excluded directories first
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            if use_ignore_files:
                dirs[:] = [
                    d for d in dirs
                    if not should_skip_directory(
                        os.path.join(root, d),
                        root_path,  # Keep using root_path as base for relative paths
                        gitignore,
                        claudeignore,
                        category_excludes
                    )
                ]

            for filename in filenames:
                rel_path = os.path.relpath(os.path.join(root, filename), root_path)

                if spec.match_file(rel_path):
                    full_path = os.path.join(root, filename)
                    if should_process_file(
                            project_config,
                            full_path,
                            filename,
                            gitignore if use_ignore_files else None,
                            root_path,
                            claudeignore if use_ignore_files else None,
                            category_excludes
                    ):
                        file_hash = process_file(full_path)
                        if file_hash:
                            files[rel_path] = file_hash

    traversal_time = time_module.time() - traversal_start
    logger.debug(f"File system traversal completed in {traversal_time:.2f} seconds")
    logger.debug(f"Found {len(files)} files to sync")

    return files

def should_process_file(
        project_config: dict,
        file_path: str,
        filename: str,
        gitignore: Optional[pathspec.PathSpec],
        base_path: str,
        claudeignore: Optional[pathspec.PathSpec],
        category_excludes: Optional[pathspec.PathSpec]
) -> bool:
    """
    Determines whether a file should be processed based on various criteria.

    Args:
        project_config (dict): Project configuration containing settings
        file_path (str): Full path to the file
        filename (str): Name of the file
        gitignore (PathSpec): PathSpec object for gitignore patterns
        base_path (str): Base path for relative path calculations
        claudeignore (PathSpec): PathSpec object for claudeignore patterns
        category_excludes (PathSpec): PathSpec object for category-specific excludes

    Returns:
        bool: True if the file should be processed, False otherwise
    """
    # Check if ignore files should be used
    use_ignore_files = project_config.get("use_ignore_files", True)

    # Get relative path for pattern matching
    rel_path = os.path.relpath(file_path, base_path)

    # Check file size
    max_file_size = project_config.get("max_file_size", 32 * 1024)
    if os.path.getsize(file_path) > max_file_size:
        logger.debug(f"File {rel_path} exceeds max size of {max_file_size} bytes")
        return False

    # Skip temporary editor files
    if filename.endswith("~"):
        logger.debug(f"Skipping temporary file {rel_path}")
        return False

    # Apply ignore patterns if enabled
    if use_ignore_files:
        # Use gitignore rules if available
        if gitignore and gitignore.match_file(rel_path):
            logger.debug(f"File {rel_path} matches gitignore pattern")
            return False

        # Use .claudeignore rules if available
        if claudeignore and claudeignore.match_file(rel_path):
            logger.debug(f"File {rel_path} matches claudeignore pattern")
            return False

    # Check category-specific exclusions
    if category_excludes and category_excludes.match_file(rel_path):
        logger.debug(f"File {rel_path} excluded by category exclusion patterns")
        return False

    # Finally check if it's a text file
    is_text = is_text_file(file_path)
    if not is_text:
        logger.debug(f"File {rel_path} is not a text file")
    return is_text

# Other utility functions remain unchanged
def load_gitignore(base_path: str) -> Optional[pathspec.PathSpec]:
    """Load gitignore patterns from base path."""
    gitignore_path = os.path.join(base_path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None

def load_claudeignore(base_path: str) -> Optional[pathspec.PathSpec]:
    """Load claudeignore patterns from base path."""
    claudeignore_path = os.path.join(base_path, ".claudeignore")
    if os.path.exists(claudeignore_path):
        with open(claudeignore_path, "r") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None

def is_text_file(file_path: str, sample_size: int = 8192) -> bool:
    """Check if a file is a text file."""
    try:
        with open(file_path, "rb") as file:
            return b"\x00" not in file.read(sample_size)
    except IOError:
        return False

def process_file(file_path: str) -> Optional[str]:
    """Process a file and return its hash."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return compute_md5_hash(content)
    except UnicodeDecodeError:
        logger.debug(f"Unable to read {file_path} as UTF-8 text. Skipping.")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
    return None

def compute_md5_hash(content: str) -> str:
    """Compute MD5 hash of content."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def should_skip_directory(dir_path: str, base_path: str, gitignore: Optional[pathspec.PathSpec],
                         claudeignore: Optional[pathspec.PathSpec],
                         category_excludes: Optional[pathspec.PathSpec]) -> bool:
    """Check if a directory should be skipped."""
    rel_path = os.path.relpath(dir_path, base_path)

    if claudeignore and claudeignore.match_file(rel_path + '/'):
        logger.debug(f"Skipping directory {rel_path} due to claudeignore pattern")
        return True

    if gitignore and gitignore.match_file(rel_path + '/'):
        logger.debug(f"Skipping directory {rel_path} due to gitignore pattern")
        return True

    if category_excludes and category_excludes.match_file(rel_path + '/'):
        logger.debug(f"Skipping directory {rel_path} due to category exclude pattern")
        return True

    return False


def handle_errors(func):
    """
    A decorator that wraps a function to catch and handle specific exceptions.

    This decorator catches exceptions of type ConfigurationError and ProviderError
    that are raised within the decorated function. When such an exception is caught,
    it prints an error message to the console using click's echo function. This is
    useful for CLI applications where a friendly error message is preferred over a
    full traceback for known error conditions.

    Args:
        func (Callable): The function to be decorated.

    Returns:
        Callable: The wrapper function that includes exception handling.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ConfigurationError, ProviderError) as e:
            click.echo(f"Error: {str(e)}")

    return wrapper


def validate_and_get_provider(config, require_org=True, require_project=False):
    """
    Validates global configuration and optionally project configuration, then returns the provider instance.

    Args:
        config (ConfigManager): The configuration manager instance containing settings
        require_org (bool): Whether to require an active organization ID. Defaults to True.
        require_project (bool): Whether to require an active project ID. Defaults to False.

    Returns:
        ClaudeAIProvider: An instance of the Claude AI provider.

    Raises:
        ConfigurationError: If required configuration is missing or invalid
    """
    # Check global settings from ~/.claudesync/config.json
    if require_org and not config.get("active_organization_id"):
        raise ConfigurationError(
            "No active organization set in global config. Please set one in ~/.claudesync/config.json"
        )

    # Verify session key
    session_key, session_key_expiry = config.get_session_key()
    if not session_key:
        raise ConfigurationError(
            f"No valid session key found for claude.ai. Please log in again."
        )

    if require_project:
        # Project settings will be loaded from the appropriate project config file
        # by the caller - we don't need to validate them here since they're
        # not part of the provider setup
        pass

    return get_provider(config)

def validate_and_store_local_path(config):
    """
    Prompts the user for the absolute path to their local project directory and stores it in the configuration.

    This function repeatedly prompts the user to enter the absolute path to their local project directory until
    a valid absolute path is provided. The path is validated to ensure it exists, is a directory, and is an absolute path.
    Once a valid path is provided, it is stored in the configuration using the `set` method of the `ConfigManager` object.

    Args:
        config (ConfigManager): The configuration manager instance to store the local path setting.

    Note:
        This function uses `click.prompt` to interact with the user, providing a default path (the current working directory)
        and validating the user's input to ensure it meets the criteria for an absolute path to a directory.
    """

    def get_default_path():
        return os.getcwd()

    while True:
        default_path = get_default_path()
        local_path = click.prompt(
            "Enter the absolute path to your local project directory",
            type=click.Path(
                exists=True, file_okay=False, dir_okay=True, resolve_path=True
            ),
            default=default_path,
            show_default=True,
        )

        if os.path.isabs(local_path):
            config.set("local_path", local_path)
            click.echo(f"Local path set to: {local_path}")
            break
        else:
            click.echo("Please enter an absolute path.")

def resolve_file_conflicts(files_by_project):
    """
    Resolve conflicts when the same file exists in multiple projects.

    Args:
        files_by_project (dict): Dictionary mapping project IDs to their files

    Returns:
        tuple: (resolved_files, conflicts)
            - resolved_files is a dictionary of files with conflicts resolved
            - conflicts is a dictionary describing the conflicts found
    """
    seen_files = {}
    conflicts = {}
    resolved_files = {}

    # Process main project first if present
    if 'main' in files_by_project:
        for file_path, file_hash in files_by_project['main'].items():
            resolved_files[file_path] = {
                'hash': file_hash,
                'project': 'main'
            }
            seen_files[file_path] = {
                'project': 'main',
                'hash': file_hash
            }

    # Process referenced projects
    for project_id, files in files_by_project.items():
        if project_id == 'main':
            continue

        for file_path, file_hash in files.items():
            if file_path in seen_files:
                # Record conflict
                conflicts[file_path] = {
                    'projects': [seen_files[file_path]['project'], project_id],
                    'hashes': [seen_files[file_path]['hash'], file_hash]
                }
                # Main project takes precedence, so we don't update resolved_files
                # if the file is already there
                if file_path not in resolved_files:
                    resolved_files[file_path] = {
                        'hash': file_hash,
                        'project': project_id
                    }
            else:
                seen_files[file_path] = {
                    'project': project_id,
                    'hash': file_hash
                }
                resolved_files[file_path] = {
                    'hash': file_hash,
                    'project': project_id
                }

    return resolved_files, conflicts

def format_conflicts_report(conflicts):
    """
    Format a human-readable report of file conflicts.

    Args:
        conflicts (dict): Dictionary of conflicts as returned by resolve_file_conflicts

    Returns:
        str: Formatted report of conflicts
    """
    if not conflicts:
        return "No conflicts found."

    report = ["File conflicts found:"]

    for file_path, conflict in conflicts.items():
        report.append(f"\nFile: {file_path}")
        report.append(f"Found in projects: {', '.join(conflict['projects'])}")

        # Check if hashes are different
        if len(set(conflict['hashes'])) > 1:
            report.append("Warning: Files have different content")
        else:
            report.append("Note: Files are identical")

        report.append(f"Using version from: {conflict['projects'][0]}")

    return "\n".join(report)
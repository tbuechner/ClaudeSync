import os
import hashlib
import time as time_module
from functools import wraps
from pathlib import Path
from typing import Dict, Optional

import click
import pathspec
import logging

from claudesync.exceptions import ConfigurationError, ProviderError
from claudesync.provider_factory import get_provider

logger = logging.getLogger(__name__)

class FileSource:
    """Tracks the source of collected files."""
    MAIN = "main"
    REFERENCED = "referenced"

class FileInfo:
    """Information about a collected file."""
    def __init__(self, path: str, hash: str, source: str, project_id: Optional[str] = None):
        self.path = path
        self.hash = hash
        self.source = source
        self.project_id = project_id

def get_local_files(config, root_path: str, files_config: dict) -> Dict[str, FileInfo]:
    """
    Get local files matching patterns in files configuration, including referenced projects.

    Args:
        config: Configuration manager instance
        root_path: Root path of the main project
        files_config: Files configuration dictionary

    Returns:
        Dict mapping file paths to FileInfo objects
    """
    logger.debug(f"Starting file collection from {root_path}")

    # Collect files from main project
    main_files = _collect_project_files(
        config,
        root_path,
        files_config,
        FileSource.MAIN
    )
    logger.debug(f"Collected {len(main_files)} files from main project")

    # Get referenced projects
    references = files_config.get('references', [])
    if not references:
        return main_files

    # Get reference paths
    try:
        active_project = config.get_active_project()[0]
        reference_paths = config._get_reference_paths(active_project)
    except ConfigurationError:
        logger.error("Failed to get reference paths")
        return main_files

    # Collect files from referenced projects
    all_files = main_files.copy()
    for ref_id in references:
        if ref_id not in reference_paths:
            logger.warning(f"No path found for referenced project {ref_id}")
            continue

        ref_config = config._load_referenced_project_config(ref_id, reference_paths)
        if not ref_config:
            logger.warning(f"Failed to load config for referenced project {ref_id}")
            continue

        # Get root path for referenced project
        ref_path = Path(reference_paths[ref_id])
        ref_root = ref_path.parent.parent  # Move up from .claudesync/config.json

        # Collect files from referenced project
        ref_files = _collect_project_files(
            config,
            str(ref_root),
            ref_config,
            FileSource.REFERENCED,
            ref_id
        )
        logger.debug(f"Collected {len(ref_files)} files from referenced project {ref_id}")

        # Handle duplicates (main project files take precedence)
        for path, file_info in ref_files.items():
            if path not in all_files:
                all_files[path] = file_info
            else:
                logger.debug(f"Skipping duplicate file from reference: {path}")

    logger.debug(f"Total files collected: {len(all_files)}")
    return all_files

def _collect_project_files(
        config,
        root_path: str,
        files_config: dict,
        source: str,
        project_id: Optional[str] = None
) -> Dict[str, FileInfo]:
    """
    Collect files from a single project (main or referenced).

    Args:
        config: Configuration manager instance
        root_path: Root path of the project
        files_config: Files configuration dictionary
        source: Source identifier (main or referenced)
        project_id: Optional project ID for referenced projects

    Returns:
        Dict mapping file paths to FileInfo objects
    """
    use_ignore_files = files_config.get("use_ignore_files", True)
    gitignore = load_gitignore(root_path) if use_ignore_files else None
    claudeignore = load_claudeignore(root_path) if use_ignore_files else None

    files = {}
    exclude_dirs = {".git", ".svn", ".hg", ".bzr", "_darcs", "CVS", "claude_chats", ".claudesync"}

    # Get push_roots from configuration
    push_roots = files_config.get("push_roots", [])
    includes = files_config.get("includes", ["*"])
    excludes = files_config.get("excludes", [])

    category_excludes = None
    if excludes:
        category_excludes = pathspec.PathSpec.from_lines("gitwildmatch", excludes)

    spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)

    # Determine roots to traverse
    roots_to_traverse = [os.path.join(root_path, root) for root in push_roots] if push_roots else [root_path]

    for base_root in roots_to_traverse:
        if not os.path.exists(base_root):
            logger.warning(f"Specified root path does not exist: {base_root}")
            continue

        for root, dirs, filenames in os.walk(base_root, topdown=True):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            if use_ignore_files:
                dirs[:] = [
                    d for d in dirs
                    if not should_skip_directory(
                        os.path.join(root, d),
                        root_path,
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
                            config,
                            full_path,
                            filename,
                            gitignore if use_ignore_files else None,
                            root_path,
                            claudeignore if use_ignore_files else None,
                            category_excludes
                    ):
                        file_hash = process_file(full_path)
                        if file_hash:
                            files[rel_path] = FileInfo(rel_path, file_hash, source, project_id)

    return files

def should_process_file(
        config_manager,
        file_path: str,
        filename: str,
        gitignore: Optional[pathspec.PathSpec],
        base_path: str,
        claudeignore: Optional[pathspec.PathSpec],
        category_excludes: Optional[pathspec.PathSpec] = None
) -> bool:
    """Determines whether a file should be processed based on various criteria."""
    use_ignore_files = config_manager.get("use_ignore_files", True)
    rel_path = os.path.relpath(file_path, base_path)

    # Check file size
    max_file_size = config_manager.get("max_file_size", 32 * 1024)
    if os.path.getsize(file_path) > max_file_size:
        logger.debug(f"File {rel_path} exceeds max size of {max_file_size} bytes")
        return False

    # Skip temporary editor files
    if filename.endswith("~"):
        logger.debug(f"Skipping temporary file {rel_path}")
        return False

    # Apply ignore patterns if enabled
    if use_ignore_files:
        if gitignore and gitignore.match_file(rel_path):
            logger.debug(f"File {rel_path} matches gitignore pattern")
            return False

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

def process_file(file_path: str) -> Optional[str]:
    """Process a single file and return its hash."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return compute_md5_hash(content)
    except UnicodeDecodeError:
        logger.debug(f"Unable to read {file_path} as UTF-8 text. Skipping.")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
    return None

def normalize_and_calculate_md5(content):
    """
    Calculate the MD5 checksum of the given content after normalizing line endings.

    This function normalizes the line endings of the input content to Unix-style (\n),
    strips leading and trailing whitespace, and then calculates the MD5 checksum of the
    normalized content. This is useful for ensuring consistent checksums across different
    operating systems and environments where line ending styles may vary.

    Args:
        content (str): The content for which to calculate the checksum.

    Returns:
        str: The hexadecimal MD5 checksum of the normalized content.
    """
    normalized_content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.md5(normalized_content.encode("utf-8")).hexdigest()

def load_gitignore(base_path):
    """
    Loads and parses the .gitignore file from the specified base path.

    This function attempts to find a .gitignore file in the given base path. If found,
    it reads the file and creates a PathSpec object that can be used to match paths
    against the patterns defined in the .gitignore file. This is useful for filtering
    out files that should be ignored based on the project's .gitignore settings.

    Args:
        base_path (str): The base directory path where the .gitignore file is located.

    Returns:
        pathspec.PathSpec or None: A PathSpec object containing the patterns from the .gitignore file
                                    if the file exists; otherwise, None.
    """
    gitignore_path = os.path.join(base_path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None

def is_text_file(file_path, sample_size=8192):
    """
    Determines if a file is a text file by checking for the absence of null bytes.

    This function reads a sample of the file (default 8192 bytes) and checks if it contains
    any null byte (\x00). The presence of a null byte is often indicative of a binary file.
    This is a heuristic method and may not be 100% accurate for all file types.

    Args:
        file_path (str): The path to the file to be checked.
        sample_size (int, optional): The number of bytes to read from the file for checking.
                                     Defaults to 8192.

    Returns:
        bool: True if the file is likely a text file, False if it is likely binary or an error occurred.
    """
    try:
        with open(file_path, "rb") as file:
            return b"\x00" not in file.read(sample_size)
    except IOError:
        return False

def compute_md5_hash(content):
    """
    Computes the MD5 hash of the given content.

    This function takes a string as input, encodes it into UTF-8, and then computes the MD5 hash of the encoded string.
    The result is a hexadecimal representation of the hash, which is commonly used for creating a quick and simple
    fingerprint of a piece of data.

    Args:
        content (str): The content for which to compute the MD5 hash.

    Returns:
        str: The hexadecimal MD5 hash of the input content.
    """
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def should_skip_directory(dir_path: str, base_path: str, gitignore, claudeignore, category_excludes) -> bool:
    """
    Check if a directory should be skipped based on ignore patterns.

    Args:
        dir_path: Path to the directory
        base_path: Root path of the project
        gitignore: PathSpec object for .gitignore patterns
        claudeignore: PathSpec object for .claudeignore patterns
        category_excludes: PathSpec object for category-specific exclude patterns

    Returns:
        bool: True if directory should be skipped, False otherwise
    """
    rel_path = os.path.relpath(dir_path, base_path)

    # Check claudeignore first since it's our primary ignore mechanism
    if claudeignore and claudeignore.match_file(rel_path + '/'):
        logger.debug(f"Skipping directory {rel_path} due to claudeignore pattern")
        return True

    # Then check gitignore
    if gitignore and gitignore.match_file(rel_path + '/'):
        logger.debug(f"Skipping directory {rel_path} due to gitignore pattern")
        return True

    # Finally check category excludes
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

def load_claudeignore(base_path):
    """
    Loads and parses the .claudeignore file from the specified base path.

    Args:
        base_path (str): The base directory path where the .claudeignore file is located.

    Returns:
        pathspec.PathSpec or None: A PathSpec object containing the patterns from the .claudeignore file
                                    if the file exists; otherwise, None.
    """
    claudeignore_path = os.path.join(base_path, ".claudeignore")
    if os.path.exists(claudeignore_path):
        with open(claudeignore_path, "r") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None


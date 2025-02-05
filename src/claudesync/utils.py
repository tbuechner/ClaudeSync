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
    def __init__(self, path: str, hash: str, source: str, project_id: Optional[str] = None, root_path: Optional[str] = None, included: bool = True):
        self.path = path
        self.hash = hash
        self.source = source
        self.project_id = project_id
        self.root_path = root_path  # Store the root path for this file
        self.included = included

def is_file_included(rel_path: str,
                   include_spec: pathspec.PathSpec,
                   exclude_spec: Optional[pathspec.PathSpec],
                   gitignore: Optional[pathspec.PathSpec],
                   claudeignore: Optional[pathspec.PathSpec],
                   category_excludes: Optional[pathspec.PathSpec],
                   use_ignore_files: bool = True) -> bool:
    """
    Determine if a file should be included based on various patterns and ignore files.

    Args:
        rel_path: Relative path of the file
        include_spec: PathSpec for inclusion patterns
        exclude_spec: PathSpec for exclusion patterns
        gitignore: PathSpec for gitignore patterns
        claudeignore: PathSpec for claudeignore patterns
        category_excludes: PathSpec for category-specific excludes
        use_ignore_files: Whether to use .gitignore and .claudeignore

    Returns:
        bool: True if the file should be included, False otherwise
    """
    # Check inclusion patterns first
    if not include_spec.match_file(rel_path):
        logger.debug(f"File {rel_path} not matched by include patterns")
        return False

    # Check exclusion patterns
    if exclude_spec and exclude_spec.match_file(rel_path):
        logger.debug(f"File {rel_path} matched by exclude patterns")
        return False

    # Check ignore files if enabled
    if use_ignore_files:
        if gitignore and gitignore.match_file(rel_path):
            logger.debug(f"File {rel_path} matched by gitignore")
            return False

        if claudeignore and claudeignore.match_file(rel_path):
            logger.debug(f"File {rel_path} matched by claudeignore")
            return False

    # Check category excludes
    if category_excludes and category_excludes.match_file(rel_path):
        logger.debug(f"File {rel_path} matched by category excludes")
        return False

    return True

def get_local_files(config, root_path: str, files_config: dict) -> Dict[str, FileInfo]:
    """Get local files matching patterns in files configuration."""
    logger.debug(f"Starting file collection from {root_path}")

    # Initialize ignore specs
    use_ignore_files = files_config.get("use_ignore_files", True)
    gitignore = load_gitignore(root_path) if use_ignore_files else None
    claudeignore = load_claudeignore(root_path) if use_ignore_files else None

    # Initialize pattern specs
    includes = files_config.get('includes', ['*'])
    excludes = files_config.get('excludes', [])
    include_spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)
    exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", excludes) if excludes else None

    logger.debug(f"Main project configuration:")
    logger.debug(f"  Include patterns: {includes}")
    logger.debug(f"  Exclude patterns: {excludes}")

    # Collect main project files
    main_files = _collect_project_files(
        config,
        root_path,
        files_config,
        FileSource.MAIN,
        include_spec=include_spec,
        exclude_spec=exclude_spec,
        gitignore=gitignore,
        claudeignore=claudeignore,
        category_excludes=None,
        use_ignore_files=use_ignore_files
    )

    # Handle referenced projects
    references = files_config.get('references', [])
    if not references:
        return main_files

    # Get reference paths
    try:
        active_project = config.get_active_project()[0]
        reference_paths = config._get_reference_paths(active_project)
    except Exception as e:
        logger.error(f"Error getting reference paths: {e}")
        return main_files

    logger.debug(f"Processing {len(references)} referenced projects: {references}")

    # Process each referenced project
    all_files = main_files.copy()
    for ref_id in references:
        logger.debug(f"\nProcessing referenced project: {ref_id}")
        try:
            ref_files = _collect_referenced_files(
                config,
                ref_id,
                reference_paths,
                use_ignore_files
            )

            # Add non-duplicate referenced files
            for path, file_info in ref_files.items():
                if path not in all_files:
                    all_files[path] = file_info
                    logger.debug(f"Added file from {ref_id}: {path}")

        except Exception as e:
            logger.error(f"Error processing reference {ref_id}: {e}")
            logger.exception("Full error:")
            continue

    return all_files

def _collect_referenced_files(config,
                              ref_id: str,
                              reference_paths: Dict[str, str],
                              use_ignore_files: bool) -> Dict[str, FileInfo]:
    """
    Collect files from a referenced project using its own configuration.
    """
    if ref_id not in reference_paths:
        logger.warning(f"No path found for referenced project {ref_id}")
        return {}

    try:
        # Load referenced project config
        ref_config = config._load_referenced_project_config(ref_id, reference_paths)
        if not ref_config:
            logger.warning(f"Failed to load config for referenced project {ref_id}")
            return {}

        # Get root path for referenced project
        ref_config_path = Path(reference_paths[ref_id])
        ref_root = ref_config_path.parent.parent  # Move up from .claudesync/config.json
        logger.debug(f"Referenced project {ref_id} root path: {ref_root}")

        # Get patterns from referenced project's config
        includes = ref_config.get('includes', ['*'])
        excludes = ref_config.get('excludes', [])

        logger.debug(f"Referenced project {ref_id} patterns:")
        logger.debug(f"  Includes: {includes}")
        logger.debug(f"  Excludes: {excludes}")

        # Create PathSpec objects
        include_spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)
        exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", excludes) if excludes else None

        # Load ignore files for referenced project
        gitignore = load_gitignore(str(ref_root)) if use_ignore_files else None
        claudeignore = load_claudeignore(str(ref_root)) if use_ignore_files else None

        # Get push roots from include patterns if not specified
        push_roots = ref_config.get('push_roots', [])
        if not push_roots:
            # Extract base directory from include patterns
            for pattern in includes:
                base_dir = pattern.split('/')[0]
                if base_dir and base_dir not in push_roots:
                    push_roots.append(base_dir)

        # If still no push roots, use project root
        roots_to_traverse = [os.path.join(str(ref_root), root) for root in push_roots] if push_roots else [str(ref_root)]
        logger.debug(f"Roots to traverse: {roots_to_traverse}")

        files = {}
        files_found = 0
        files_included = 0

        for base_root in roots_to_traverse:
            if not os.path.exists(base_root):
                logger.warning(f"Root path does not exist: {base_root}")
                continue

            for root, dirs, filenames in os.walk(base_root, topdown=True):
                # Get path relative to project root for pattern matching
                rel_root = os.path.relpath(root, str(ref_root))

                # Filter directories to avoid unnecessary traversal
                dirs[:] = [d for d in dirs if d not in {".git", ".svn", ".hg", ".bzr", "_darcs", "CVS", "claude_chats", ".claudesync"}]

                # Apply ignore files if enabled
                if use_ignore_files:
                    dirs[:] = [
                        d for d in dirs
                        if not should_skip_directory(
                            os.path.join(root, d),
                            str(ref_root),
                            gitignore,
                            claudeignore,
                            None
                        )
                    ]

                for filename in filenames:
                    try:
                        abs_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(abs_path, str(ref_root))
                        files_found += 1

                        # Check if file matches include pattern
                        matches_include = include_spec.match_file(rel_path)
                        matches_exclude = exclude_spec.match_file(rel_path) if exclude_spec else False

                        if matches_include and not matches_exclude:
                            if should_process_file(
                                    config,
                                    abs_path,
                                    filename,
                                    gitignore if use_ignore_files else None,
                                    str(ref_root),
                                    claudeignore if use_ignore_files else None,
                                    None
                            ):
                                file_hash = process_file(abs_path)
                                if file_hash:
                                    files[rel_path] = FileInfo(
                                        path=rel_path,
                                        hash=file_hash,
                                        source=FileSource.REFERENCED,
                                        project_id=ref_id,
                                        root_path=str(ref_root),
                                        included=True
                                    )
                                    files_included += 1
                                    logger.debug(f"Included file: {rel_path}")

                    except Exception as e:
                        logger.error(f"Error processing file {filename}: {e}")
                        continue

        logger.debug(f"Project {ref_id} summary:")
        logger.debug(f"  Files found: {files_found}")
        logger.debug(f"  Files included: {files_included}")
        logger.debug(f"  Files matched patterns: {len(files)}")

        return files

    except Exception as e:
        logger.error(f"Error collecting files for referenced project {ref_id}: {str(e)}")
        logger.exception("Full error:")
        return {}

def _collect_project_files(config,
                           root_path: str,
                           files_config: dict,
                           source: str,
                           include_spec: pathspec.PathSpec,
                           exclude_spec: Optional[pathspec.PathSpec],
                           gitignore: Optional[pathspec.PathSpec],
                           claudeignore: Optional[pathspec.PathSpec],
                           category_excludes: Optional[pathspec.PathSpec],
                           use_ignore_files: bool,
                           project_id: Optional[str] = None) -> Dict[str, FileInfo]:
    """Collect files from a single project directory."""
    files = {}
    exclude_dirs = {".git", ".svn", ".hg", ".bzr", "_darcs", "CVS", "claude_chats", ".claudesync"}
    files_found = 0
    files_included = 0

    # Get push_roots from configuration
    push_roots = files_config.get("push_roots", [])

    # If no push_roots specified, try to derive from include patterns
    if not push_roots and source == FileSource.MAIN:
        includes = files_config.get('includes', ['*'])
        # Extract base directories from include patterns
        for pattern in includes:
            if pattern == '*':
                continue
            base_dir = pattern.split('/')[0]  # This treats "*.py" as a directory
            if base_dir and base_dir != '*' and base_dir not in push_roots:
                push_roots.append(base_dir)


    roots_to_traverse = [os.path.join(root_path, root) for root in push_roots] if push_roots else [root_path]
    logger.debug(f"Traversing roots for {source}: {roots_to_traverse}")

    for base_root in roots_to_traverse:
        if not os.path.exists(base_root):
            logger.warning(f"Root path does not exist: {base_root}")
            continue

        for root, dirs, filenames in os.walk(base_root, topdown=True):
            # Get path relative to project root for pattern matching
            rel_root = os.path.relpath(root, root_path)

            # Filter directories
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
                try:
                    files_found += 1
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, root_path)

                    # Check file against patterns
                    matches_include = include_spec.match_file(rel_path)
                    matches_exclude = exclude_spec.match_file(rel_path) if exclude_spec else False

                    logger.debug(f"Checking file: {rel_path}")
                    logger.debug(f"  Matches include: {matches_include}")
                    logger.debug(f"  Matches exclude: {matches_exclude}")

                    if matches_include and not matches_exclude:
                        if should_process_file(
                                config,
                                abs_path,
                                filename,
                                gitignore if use_ignore_files else None,
                                root_path,
                                claudeignore if use_ignore_files else None,
                                category_excludes
                        ):
                            file_hash = process_file(abs_path)
                            if file_hash:
                                files[rel_path] = FileInfo(
                                    path=rel_path,
                                    hash=file_hash,
                                    source=source,
                                    project_id=project_id,
                                    root_path=root_path,
                                    included=True
                                )
                                files_included += 1
                                logger.debug(f"Included file: {rel_path}")

                except Exception as e:
                    logger.error(f"Error processing file {filename}: {e}")
                    continue

    logger.debug(f"Collection summary for {source}:")
    logger.debug(f"  Files found: {files_found}")
    logger.debug(f"  Files included: {files_included}")
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


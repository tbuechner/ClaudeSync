import os
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple, Union
import json

from .exceptions import ConfigurationError
from .utils import get_local_files

logger = logging.getLogger(__name__)

class ProjectReferencesManager:
    """
    Manages project references and their configurations.

    This class handles loading, validating, and resolving referenced projects
    in a ClaudeSync project. It works with both the public project configuration
    and private project ID mappings.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the ProjectReferencesManager.

        Args:
            config_dir (Path, optional): Path to .claudesync directory
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = self._find_config_dir()

    def _find_config_dir(self) -> Optional[Path]:
        """Find the nearest .claudesync directory from current directory upwards."""
        current_dir = Path.cwd()
        root_dir = Path(current_dir.root)

        if current_dir != root_dir:
            config_dir = current_dir / ".claudesync"
            if config_dir.is_dir():
                return config_dir

        return None

    def get_referenced_projects(self, project_path: str) -> Dict[str, Path]:
        """
        Get the referenced projects and their absolute paths for a given project.

        Args:
            project_path (str): Path to the project configuration

        Returns:
            Dict[str, Path]: Dictionary mapping project IDs to their configuration file paths

        Raises:
            ConfigurationError: If references cannot be resolved or are invalid
        """
        # Get project configuration files
        project_config = self._get_project_config(project_path)
        project_id_config = self._get_project_id_config(project_path)

        # Get referenced project identifiers
        referenced_projects = project_config.get('references', [])
        logger.debug(f"Found referenced projects: {referenced_projects}")

        # Get reference paths
        reference_paths = project_id_config.get('reference_paths', {})
        logger.debug(f"Found reference paths: {reference_paths}")

        # Validate and resolve paths
        resolved_references: Dict[str, Path] = {}

        for ref_id in referenced_projects:
            if ref_id not in reference_paths:
                raise ConfigurationError(
                    f"Referenced project '{ref_id}' has no path mapping in project_id.json"
                )

            ref_path = Path(reference_paths[ref_id])
            logger.debug(f"Processing reference '{ref_id}' with path: {ref_path}")

            # Validate referenced project path
            if not ref_path.is_absolute():
                raise ConfigurationError(
                    f"Referenced project path must be absolute: {ref_path}"
                )

            if not self._is_valid_project_path(ref_path):
                raise ConfigurationError(
                    f"Invalid referenced project path: {ref_path}"
                )

            resolved_references[ref_id] = ref_path
            logger.debug(f"Successfully resolved reference '{ref_id}' to: {ref_path}")

        return resolved_references

    def get_all_project_files(self, project_path: str) -> Dict[str, Dict[str, str]]:
        """
        Get all files from main project and referenced projects.

        Args:
            project_path (str): Path to the main project

        Returns:
            Dict[str, Dict[str, str]]: Dictionary mapping project IDs to their file dictionaries
                                    Each file dictionary maps relative file paths to their hashes
        """
        files_by_project = {}

        # Get main project files first
        main_config = self._get_project_config(project_path)
        main_root = self.config_dir.parent if self.config_dir else None

        if not main_root:
            raise ConfigurationError("Could not determine project root directory")

        logger.debug(f"Processing main project files from root: {main_root}")
        files_by_project['main'] = get_local_files(main_config, main_root, main_config)
        logger.debug(f"Found {len(files_by_project['main'])} files in main project")

        try:
            # Get referenced project files
            referenced_projects = self.get_referenced_projects(project_path)

            for ref_id, ref_path in referenced_projects.items():
                logger.debug(f"Processing referenced project {ref_id} at {ref_path}")
                try:
                    # Get referenced project configuration
                    with open(ref_path, 'r') as f:
                        ref_config = json.load(f)

                    # Get the actual root directory for the referenced project
                    ref_root = ref_path.parent.parent  # Navigate up from .project.json
                    logger.debug(f"Using reference root: {ref_root}")

                    # Collect files using the referenced project's root
                    ref_files = get_local_files(ref_config, str(ref_root), ref_config)
                    logger.debug(f"Found {len(ref_files)} files in referenced project {ref_id}")

                    # Store files with project ID
                    files_by_project[ref_id] = ref_files

                except (IOError, json.JSONDecodeError) as e:
                    logger.warning(f"Error reading referenced project {ref_id}: {e}")
                    continue

        except ConfigurationError as e:
            logger.warning(f"Error processing referenced projects: {e}")
            # Continue with just main project files
            pass

        return files_by_project

    def _get_project_config(self, project_path: Union[str, Path]) -> dict:
        """
        Get the project configuration containing references.

        Args:
            project_path (str | Path): Path to the project or full path to .project.json

        Returns:
            dict: Project configuration

        Raises:
            ConfigurationError: If project configuration cannot be found or is invalid
        """
        project_path_str = str(project_path)

        # Handle full path to .project.json
        if project_path_str.endswith('.project.json') and os.path.isfile(project_path_str):
            project_file = Path(project_path_str)
        else:
            # Handle regular project identifiers
            if not self.config_dir:
                raise ConfigurationError("No .claudesync directory found")

            project_file = self.config_dir / f"{project_path}.project.json"

            # Handle nested project paths
            if not project_file.exists():
                parts = str(project_path).split('/')
                project_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project.json"

            if not project_file.exists():
                raise ConfigurationError(f"Project configuration not found for {project_path}")

        logger.debug(f"Reading project configuration from: {project_file}")
        try:
            with open(project_file) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid project configuration: {str(e)}")

    def _get_project_id_config(self, project_path: str) -> dict:
        """
        Get the project ID configuration containing reference paths.

        Args:
            project_path (str): Path to the project

        Returns:
            dict: Project ID configuration

        Raises:
            ConfigurationError: If project ID configuration cannot be found or is invalid
        """
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        project_id_file = self.config_dir / f"{project_path}.project_id.json"

        # Handle nested project paths
        if not project_id_file.exists():
            parts = project_path.split('/')
            project_id_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project_id.json"

        if not project_id_file.exists():
            raise ConfigurationError(f"Project ID configuration not found for {project_path}")

        logger.debug(f"Reading project ID configuration from: {project_id_file}")
        try:
            with open(project_id_file) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid project ID configuration: {str(e)}")

    def _is_valid_project_path(self, path: Path) -> bool:
        """
        Validate that a path points to a valid project.json file.

        Args:
            path (Path): Path to the .project.json file

        Returns:
            bool: True if path is valid, False otherwise
        """
        try:
            # Check that file exists and ends with .project.json
            if not path.exists() or not path.is_file():
                logger.debug(f"Path {path} does not exist or is not a file")
                return False

            if not path.name.endswith('.project.json'):
                logger.debug(f"Path {path} does not point to a .project.json file")
                return False

            # Try to read and parse the JSON file
            with open(path, 'r') as f:
                json.load(f)
                return True

        except json.JSONDecodeError:
            logger.debug(f"File {path} is not a valid JSON file")
            return False
        except IOError:
            logger.debug(f"Could not read file {path}")
            return False
        except Exception as e:
            logger.warning(f"Error validating project path {path}: {str(e)}")
            return False

        return True
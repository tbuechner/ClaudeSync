import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, TypedDict
import json
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

class ProjectReference(TypedDict):
    project: str
    excludes: Optional[List[str]]

class ProjectReferenceHandler:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    def get_reference_paths(self, project_path: str) -> Dict[str, Path]:
        """
        Get resolved paths for all referenced projects.
        Resolves paths relative to the main project's root directory.
        """
        try:
            # Get main project's configuration
            files_config = self.config_manager.get_files_config(project_path)
            references = files_config.get('references', [])

            if not references:
                return {}

            main_project_root = self.config_manager.get_project_root()
            if not main_project_root:
                raise ConfigurationError("Could not determine project root")

            resolved_paths = {}
            for ref in references:
                ref_project = ref['project']
                ref_parts = Path(ref_project).parts

                # For project "repos/cplace-utility-widgets/tree_table_widget",
                # we want to get to /repos/cplace-utility-widgets
                base_path = Path(main_project_root).parent
                for part in ref_parts[:-1]:
                    base_path = base_path / part
                project_root = base_path.resolve()

                logger.debug(f"Checking referenced project at: {project_root}")

                if self._validate_reference_path(project_root, ref_parts[-1]):
                    resolved_paths[ref_project] = project_root
                else:
                    logger.warning(f"Referenced project path not found: {project_root}")
                    continue

            return resolved_paths

        except ConfigurationError as e:
            logger.error(f"Error reading project configuration: {e}")
            return {}

    def get_project_references(self, project_path: str) -> List[ProjectReference]:
        """Get all project references from configuration."""
        try:
            files_config = self.config_manager.get_files_config(project_path)
            return files_config.get('references', [])
        except ConfigurationError:
            return []

    def collect_referenced_files(self, project_path: str, base_files: Dict[str, str]) -> Dict[str, str]:
        """
        Collect files from referenced projects and merge with base files.

        Args:
            project_path: Path of the main project
            base_files: Dictionary of already collected files from main project

        Returns:
            Dict[str, str]: Merged dictionary of all files including references
        """
        from .utils import get_local_files  # Import here to avoid circular dependency

        # Get references and their paths
        references = self.get_project_references(project_path)
        reference_paths = self.get_reference_paths(project_path)

        # Start with base files
        all_files = base_files.copy()

        # Process each reference
        for ref in references:
            ref_project = ref['project']
            ref_path = reference_paths.get(ref_project)

            if not ref_path:
                logger.warning(f"Missing path for referenced project: {ref_project}")
                continue

            try:
                # Get referenced project's config
                ref_config = self._get_referenced_project_config(ref_path, ref_project)

                # Merge excludes from the reference definition with the referenced project's excludes
                ref_excludes = ref_config.get('excludes', [])
                if 'excludes' in ref:
                    ref_excludes.extend(ref['excludes'])
                ref_config['excludes'] = ref_excludes

                # Collect files from referenced project
                ref_files = get_local_files(
                    self.config_manager,
                    ref_path,
                    ref_config,
                    include_references=False  # Prevent circular references
                )

                # Merge files (main project files take precedence)
                for file_path, file_hash in ref_files.items():
                    if file_path not in all_files:
                        all_files[file_path] = file_hash

            except ConfigurationError as e:
                logger.warning(f"Error processing reference {ref_project}: {e}")
                continue

        return all_files

    def _validate_reference_path(self, path: Path, ref_project: str) -> bool:
        """
        Validate that a referenced project path is valid.

        Args:
            path: Absolute path to referenced project
            ref_project: Project identifier

        Returns:
            bool: True if path is valid, False otherwise
        """
        if not path.exists():
            logger.warning(f"Referenced project path does not exist: {path}")
            return False

        # Check for .claudesync directory
        if not (path / '.claudesync').exists():
            logger.warning(f"No .claudesync directory found in referenced project: {path}")
            return False

        # Check for project configuration
        project_config = path / '.claudesync' / f"{ref_project}.project.json"
        if not project_config.exists():
            logger.warning(f"No project configuration found for referenced project: {path}")
            return False

        return True

    def _get_referenced_project_config(self, ref_path: Path, ref_project: str) -> dict:
        """Get configuration for a referenced project."""
        # Get the project name from the last part of the path
        project_name = ref_project.split('/')[-1]
        config_file = ref_path / '.claudesync' / f"{project_name}.project.json"
        try:
            with open(config_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise ConfigurationError(f"Error reading referenced project config: {e}")
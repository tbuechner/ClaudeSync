import json
import os
from datetime import datetime
from pathlib import Path
import logging
from typing import Dict, Optional, List

from claudesync.configmanager.base_config_manager import BaseConfigManager
from claudesync.exceptions import ConfigurationError
from claudesync.session_key_manager import SessionKeyManager


class FileConfigManager(BaseConfigManager):
    """
    Manages the configuration for ClaudeSync, handling both global and local (project-specific) settings.

    This class provides methods to load, save, and access configuration settings from both
    a global configuration file (~/.claudesync/config.json) and a local configuration file
    (.claudesync/config.local.json) in the project directory. Session keys are stored separately
    in provider-specific files.
    """

    def __init__(self, config_dir=None):
        """
        Initialize the ConfigManager.

        Sets up paths for global and local configuration files and loads both configurations.
        """
        super().__init__()
        self.global_config_dir = Path.home() / ".claudesync"
        self.global_config_file = self.global_config_dir / "config.json"
        self.global_config = self._load_global_config()
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = self._find_config_dir()

        # Cache for referenced project configurations
        self._referenced_configs_cache = {}

    # Start Referenced projects

    def get_files_config(self, project_path: str, include_references: bool = True) -> dict:
        """
        Get files configuration from files-specific JSON file, optionally including referenced projects.

        Args:
            project_path: Path to the project like 'datamodel/typeconstraints'
            include_references: Whether to include configurations from referenced projects

        Returns:
            dict: Combined configuration including referenced projects if specified
        """
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        # Get main project config
        main_config = self._load_project_config(project_path)

        if not include_references:
            return main_config

        # Handle referenced projects
        references = main_config.get('references', [])
        if not references:
            return main_config

        # Get reference paths
        reference_paths = self._get_reference_paths(project_path)
        if not reference_paths:
            return main_config

        # Combine configurations
        combined_config = main_config.copy()
        referenced_files = []

        for ref_id in references:
            ref_config = self._load_referenced_project_config(ref_id, reference_paths)
            if ref_config:
                referenced_files.extend(self._process_reference_config(ref_config))

        if referenced_files:
            combined_config['referenced_files'] = referenced_files

        return combined_config

    def _load_project_config(self, project_path: str) -> dict:
        """Load the main project configuration file."""
        files_file = self._get_project_config_path(project_path)
        if not files_file.exists():
            raise ConfigurationError(f"Project configuration not found for {project_path}")

        with open(files_file) as f:
            return json.load(f)

    def _get_project_config_path(self, project_path: str) -> Path:
        """Get the path to a project's configuration file."""
        files_file = self.config_dir / f"{project_path}.project.json"
        if not files_file.exists():
            # Try with subdirectories
            parts = project_path.split('/')
            files_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project.json"
        return files_file

    def _get_reference_paths(self, project_path: str) -> Dict[str, str]:
        """
        Get the reference paths from project_id configuration.

        Args:
            project_path: Path to the project

        Returns:
            dict: Mapping of reference IDs to their absolute paths
        """
        project_id_file = self.config_dir / f"{project_path}.project_id.json"
        if not project_id_file.exists():
            # Try with subdirectories
            parts = project_path.split('/')
            project_id_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project_id.json"

        if not project_id_file.exists():
            return {}

        with open(project_id_file) as f:
            config = json.load(f)
            return config.get('reference_paths', {})

    def _load_referenced_project_config(self, ref_id: str, reference_paths: Dict[str, str]) -> Optional[dict]:
        """
        Load and validate a referenced project's configuration.

        Args:
            ref_id: Reference identifier
            reference_paths: Mapping of reference IDs to paths

        Returns:
            dict or None: Referenced project configuration if valid
        """
        # Check cache first
        if ref_id in self._referenced_configs_cache:
            return self._referenced_configs_cache[ref_id]

        # Get reference path
        ref_path = reference_paths.get(ref_id)
        if not ref_path:
            logging.warning(f"No path found for referenced project {ref_id}")
            return None

        # Validate path
        ref_path = Path(ref_path)
        if not self._validate_reference_path(ref_path):
            return None

        try:
            with open(ref_path) as f:
                config = json.load(f)
                self._referenced_configs_cache[ref_id] = config
                return config
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading referenced project {ref_id}: {str(e)}")
            return None

    def _validate_reference_path(self, path: Path) -> bool:
        """
        Validate a referenced project path for security and correctness.

        Args:
            path: Path to validate

        Returns:
            bool: True if path is valid
        """
        try:
            # Must be absolute
            if not path.is_absolute():
                logging.error(f"Referenced path must be absolute: {path}")
                return False

            # Must exist and be readable
            if not path.exists() or not os.access(path, os.R_OK):
                logging.error(f"Referenced path not accessible: {path}")
                return False

            # Must be within a .claudesync directory
            if '.claudesync' not in path.parts:
                logging.error(f"Referenced path must be within .claudesync directory: {path}")
                return False

            # No symlinks allowed
            if path.is_symlink():
                logging.error(f"Symlinks not allowed in reference paths: {path}")
                return False

            return True

        except Exception as e:
            logging.error(f"Error validating reference path {path}: {str(e)}")
            return False

    def _process_reference_config(self, config: dict) -> List[dict]:
        """
        Process a referenced project's configuration.

        Args:
            config: Referenced project configuration

        Returns:
            list: List of file configurations from referenced project
        """
        includes = config.get('includes', [])
        excludes = config.get('excludes', [])

        return [{
            'pattern': pattern,
            'exclude': pattern in excludes
        } for pattern in includes]

    def validate_references(self, project_path: str) -> List[str]:
        """
        Validate all references for a project and return any errors.

        Args:
            project_path: Path to the project to validate

        Returns:
            list: List of error messages, empty if all valid
        """
        errors = []

        try:
            main_config = self._load_project_config(project_path)
            references = main_config.get('references', [])

            if not references:
                return errors

            reference_paths = self._get_reference_paths(project_path)

            for ref_id in references:
                if ref_id not in reference_paths:
                    errors.append(f"No path configured for reference '{ref_id}'")
                    continue

                ref_path = Path(reference_paths[ref_id])
                if not self._validate_reference_path(ref_path):
                    errors.append(f"Invalid reference path for '{ref_id}': {ref_path}")

        except Exception as e:
            errors.append(f"Error validating references: {str(e)}")

        return errors

    def clear_reference_cache(self):
        """Clear the cached referenced project configurations."""
        self._referenced_configs_cache.clear()

    # End Referenced projects

    def get_projects(self, include_unlinked=False):
        """
        Get all projects configured in the .claudesync directory.

        Returns:
            dict: A dictionary mapping project paths to their IDs
            Example: {
                'datamodel/typeconstraints': 'project-uuid-1',
                'myproject': 'project-uuid-2'
            }

        Raises:
            ConfigurationError: If no .claudesync directory is found
        """
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        projects = {}

        # Walk through the .claudesync directory
        for root, _, files in os.walk(self.config_dir):
            for file in files:
                if file.endswith('.project.json'):
                    # Extract project path from filename
                    project_path = file[:-len('.project.json')]

                    project_id_file = os.path.join(root, project_path + '.project_id.json')
                    project_id = ''

                    # Handle nested projects by getting relative path from .claudesync dir
                    rel_root = os.path.relpath(root, self.config_dir)
                    if rel_root != '.':
                        project_path = os.path.join(rel_root, project_path)

                    if os.path.exists(project_id_file):
                        # Load project ID from file
                        try:
                            with open(project_id_file) as f:
                                project_data = json.load(f)
                                project_id = project_data.get('project_id')
                        except (json.JSONDecodeError, IOError) as e:
                            logging.warning(f"Failed to load project file {file}: {str(e)}")
                            continue

                    projects[project_path] = project_id
        return projects

    def get_active_project(self):
        """
        Get the currently active project.

        Returns:
            tuple: (project_path, project_id) if an active project exists, (None, None) otherwise
        """
        if not self.config_dir:
            return None, None

        active_project_file = self.config_dir / "active_project.json"
        if not active_project_file.exists():
            return None, None

        try:
            with open(active_project_file) as f:
                data = json.load(f)
                return data.get("project_path"), data.get("project_id")
        except (json.JSONDecodeError, IOError):
            return None, None

    def set_active_project(self, project_path, project_id):
        """
        Set the active project.

        Args:
            project_path (str): Path to the project like 'datamodel/typeconstraints'
            project_id (str): UUID of the project
        """
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        active_project_file = self.config_dir / "active_project.json"

        data = {
            "project_path": project_path,
            "project_id": project_id
        }

        with open(active_project_file, "w") as f:
            json.dump(data, f, indent=2)

    def _find_config_dir(self):
        current_dir = Path.cwd()
        root_dir = Path(current_dir.root)

        if current_dir != root_dir:
            config_dir = current_dir / ".claudesync"

            # Create the directory if it doesn't exist
            config_dir.mkdir(exist_ok=True)

            if config_dir.is_dir():
                return config_dir

        return None

    def get_project_id(self, project_path):
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        project_file = self.config_dir / f"{project_path}.project_id.json"
        if not project_file.exists():
            # Try with subdirectories
            parts = project_path.split('/')
            project_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project_id.json"

        if not project_file.exists():
            raise ConfigurationError(f"Project configuration not found for {project_path}")

        with open(project_file) as f:
            return json.load(f)['project_id']

    def get_files_config(self, project_path):
        """Get files configuration from files-specific JSON file."""
        if not self.config_dir:
            raise ConfigurationError("No .claudesync directory found")

        files_file = self.config_dir / f"{project_path}.project.json"
        if not files_file.exists():
            # Try with subdirectories
            parts = project_path.split('/')
            files_file = self.config_dir / '/'.join(parts[:-1]) / f"{parts[-1]}.project.json"

        if not files_file.exists():
            raise ConfigurationError(f"Files configuration not found for {project_path}")

        with open(files_file) as f:
            return json.load(f)

    def get_project_root(self):
        """Get the root directory containing .claudesync."""
        return self.config_dir.parent if self.config_dir else None


    def _load_global_config(self):
        """
        Loads the global configuration from the JSON file.

        If the configuration file doesn't exist, it creates the directory (if necessary)
        and returns the default configuration.

        Returns:
            dict: The loaded global configuration with default values for missing keys.
        """
        if not self.global_config_file.exists():
            self.global_config_dir.mkdir(parents=True, exist_ok=True)
            return self._get_default_config()

        with open(self.global_config_file, "r") as f:
            config = json.load(f)
            defaults = self._get_default_config()
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
            return config

    def get_local_path(self):
        """
        Retrieves the path of the directory containing the .claudesync folder.

        Returns:
            str: The path of the directory containing the .claudesync folder, or None if not found.
        """
        if not self.config_dir:
            return None
        # Return the parent directory of .claudesync folder which is the project root
        return str(self.config_dir.parent)

    def get(self, key, default=None):
        """
        Retrieves a configuration value.

        Checks the local configuration first, then falls back to the global configuration.

        Args:
            key (str): The key for the configuration setting to retrieve.
            default (any, optional): The default value to return if the key is not found. Defaults to None.

        Returns:
            The value of the configuration setting if found, otherwise the default value.
        """
        return self.local_config.get(key) or self.global_config.get(key, default)

    def set(self, key, value, local=False):
        """
        Sets a configuration value and saves the configuration.

        Args:
            key (str): The key for the configuration setting to set.
            value (any): The value to set for the given key.
            local (bool): If True, sets the value in the local configuration. Otherwise, sets it in the global configuration.
        """
        if local:
            # Update local_config_dir when setting local_path
            if key == "local_path":
                self.local_config_dir = Path(value)
                # Create .claudesync directory in the specified path
                (self.local_config_dir / ".claudesync").mkdir(exist_ok=True)

            self.local_config[key] = value
            self._save_local_config()
        else:
            self.global_config[key] = value
            self._save_global_config()

    def _save_global_config(self):
        """
        Saves the current global configuration to the JSON file.

        This method writes the current state of the `global_config` attribute to the configuration file,
        pretty-printing the JSON for readability.
        """
        with open(self.global_config_file, "w") as f:
            json.dump(self.global_config, f, indent=2)

    def _save_local_config(self):
        """
        Saves the current local configuration to the .claudesync/config.local.json file.
        """
        if self.local_config_dir:
            local_config_file = (
                self.local_config_dir / ".claudesync" / "config.local.json"
            )
            local_config_file.parent.mkdir(exist_ok=True)
            with open(local_config_file, "w") as f:
                json.dump(self.local_config, f, indent=2)

    def set_session_key(self, session_key, expiry):
        """
        Sets the session key and its expiry for a specific provider.

        Args:
            session_key (str): The session key to set.
            expiry (datetime): The expiry datetime for the session key.
        """
        try:
            session_key_manager = SessionKeyManager()
            encrypted_session_key, encryption_method = (
                session_key_manager.encrypt_session_key(session_key)
            )

            self.global_config_dir.mkdir(parents=True, exist_ok=True)
            provider_key_file = self.global_config_dir / f"claude.ai.key"
            with open(provider_key_file, "w") as f:
                json.dump(
                    {
                        "session_key": encrypted_session_key,
                        "session_key_encryption_method": encryption_method,
                        "session_key_expiry": expiry.isoformat(),
                    },
                    f,
                )
        except RuntimeError as e:
            logging.error(f"Failed to encrypt session key: {str(e)}")
            raise

    def get_session_key(self):
        """
        Retrieves the session key if it's still valid.

        Returns:
            tuple: A tuple containing the session key and expiry if valid, (None, None) otherwise.
        """
        provider_key_file = self.global_config_dir / f"claude.ai.key"
        if not provider_key_file.exists():
            return None, None

        with open(provider_key_file, "r") as f:
            data = json.load(f)

        encrypted_key = data.get("session_key")
        encryption_method = data.get("session_key_encryption_method")
        expiry_str = data.get("session_key_expiry")

        if not encrypted_key or not expiry_str:
            return None, None

        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now() > expiry:
            return None, None

        try:
            session_key_manager = SessionKeyManager()
            session_key = session_key_manager.decrypt_session_key(
                encryption_method, encrypted_key
            )
            return session_key, expiry
        except RuntimeError as e:
            logging.error(f"Failed to decrypt session key: {str(e)}")
            return None, None

    def clear_all_session_keys(self):
        """
        Removes all stored session keys.
        """
        for file in self.global_config_dir.glob("*.key"):
            os.remove(file)

    def get_providers_with_session_keys(self):
        """
        Retrieves a list of providers that have valid session keys.

        Returns:
            list: A list of provider names with valid session keys.
        """
        providers = []
        for file in self.global_config_dir.glob("claude.ai.key"):
            provider = file.stem
            session_key, expiry = self.get_session_key()
            if session_key and expiry > datetime.now():
                providers.append(provider)
        return providers

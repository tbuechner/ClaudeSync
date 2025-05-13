# Configuration Manager

This directory contains the configuration management infrastructure for ClaudeSync. It provides a robust framework for handling both global and local (project-specific) configuration settings, allowing for flexible and hierarchical configuration across different environments.

## Source Files

### `base_config_manager.py`

**Primary Purpose**: Defines the abstract base class that sets the foundation for all configuration management implementations.

**Key Components**:
- `BaseConfigManager` (abstract class): Establishes the interface for configuration management with methods for accessing and modifying configuration settings.
- Provides default configuration values and utility methods shared across all implementations.

**Dependencies**:
- Python standard libraries: `abc` (for abstract base class), `copy` (for deep copying configurations)

### `file_config_manager.py`

**Primary Purpose**: Implements a file-based configuration manager that stores settings in JSON files.

**Key Components**:
- `FileConfigManager` class: Concrete implementation of `BaseConfigManager` that reads/writes configuration to the filesystem.
- Handles global configuration in `~/.claudesync/config.json`
- Manages local project configurations in `.claudesync/` directories
- Provides functionality for session key management with encryption/decryption

**Dependencies**:
- `base_config_manager.py`: Inherits from `BaseConfigManager`
- `claudesync.exceptions`: Uses `ConfigurationError`
- `claudesync.session_key_manager`: Relies on `SessionKeyManager` for secure credential storage
- Python standard libraries: `json`, `os`, `datetime`, `pathlib`, `logging`

### `__init__.py`

**Primary Purpose**: Manages module exports and provides a clean interface for importing the configuration classes.

**Key Components**:
- Exports `BaseConfigManager` and `FileConfigManager` classes
- Defines `__all__` to control what is imported with `from claudesync.configmanager import *`

**Dependencies**:
- Internal imports from `.base_config_manager` and `.file_config_manager`

## Subdirectories

### `__pycache__`

This is a Python-generated directory containing compiled bytecode files. Not intended for direct user interaction and should be ignored during source control operations.

## Usage Context

### When to Analyze These Files

- When working with configuration handling in ClaudeSync
- When adding new configuration options or settings
- When implementing a new configuration storage backend
- When troubleshooting configuration-related issues

### Common Tasks

- Retrieving project configurations and IDs
- Managing session keys securely
- Setting default synchronization categories
- Getting and setting configuration values (both global and local)
- Finding project roots and configuration directories

### Relationship with Other Directories

- The configuration manager is a fundamental component used throughout the ClaudeSync codebase
- It provides configuration information to other components like synchronizers and file handlers
- It interacts with the authentication system via the `session_key_manager` module

## Design Patterns and Architecture

1. **Abstract Factory Pattern**: The code employs an abstract base class (`BaseConfigManager`) that defines the interface for configuration management, with concrete implementations like `FileConfigManager`.

2. **Separation of Concerns**: Configuration handling is separated into global (user-level) and local (project-level) contexts, allowing for hierarchical configuration.

3. **Secure Credential Management**: Session keys are encrypted before storage and decrypted when needed, following security best practices.

4. **Configuration Discovery**: The system automatically discovers configuration files by traversing directories, enabling a flexible project structure.

5. **Default Values**: The code provides sensible defaults for configuration settings, making it more user-friendly while still allowing customization.

## Special Notes

- Configuration files are stored in JSON format for human readability and easy editing
- Global configuration is stored in the user's home directory (`~/.claudesync/`)
- Local project configuration is stored in a `.claudesync/` directory within each project
- Session keys have an expiration mechanism to enhance security

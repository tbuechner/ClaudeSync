# ClaudeSync Core

This directory contains the core components of the ClaudeSync application, which enables synchronization between local files and Claude AI projects.

## Overview

ClaudeSync is a tool designed to facilitate the synchronization of local files with Claude AI projects, enabling efficient AI-assisted development workflows. The core modules in this directory handle configuration management, file synchronization, provider integration, compression algorithms, and utility functions.

## Source Files

### Primary Files

#### syncmanager.py
- **Primary Purpose**: Manages the synchronization process between local and remote files
- **Key Functions**:
  - `SyncManager` class: Handles file uploads, downloads, and delta synchronization
  - `sync()`: Main synchronization method that orchestrates the sync process
  - File comparison using MD5 hashes and timestamp-based updates
  - Support for two-way sync and remote file pruning
- **Dependencies**: compression.py, utils.py, exceptions.py

#### provider_factory.py
- **Primary Purpose**: Factory for creating provider instances
- **Key Functions**:
  - `get_provider()`: Returns an instance of the appropriate provider
- **Dependencies**: providers/claude_ai.py

#### compression.py
- **Primary Purpose**: Provides file compression algorithms for efficient file transfers
- **Key Functions**:
  - Multiple compression implementations (zlib, bz2, lzma, brotli, etc.)
  - File packing and unpacking utilities for batched transfers
  - Content compression and decompression with various algorithms
- **Dependencies**: Uses Python standard libraries for compression

#### token_counter.py
- **Primary Purpose**: Counts tokens in text content for Claude AI
- **Key Functions**:
  - `TokenCounter` class: Counts tokens in text using TikToken with cl100k_base encoding
  - `count_project_tokens()`: Analyzes token usage across multiple files
- **Dependencies**: tiktoken, utils.py

#### session_key_manager.py
- **Primary Purpose**: Manages and secures Claude AI session keys
- **Key Functions**:
  - `SessionKeyManager` class: Handles encryption/decryption of session keys
  - Key generation, derivation, and secure storage
  - Support for different SSH key types (ed25519, ecdsa)
- **Dependencies**: cryptography library

#### utils.py
- **Primary Purpose**: Provides utility functions used throughout the codebase
- **Key Functions**:
  - File handling utilities (hash calculations, text file detection)
  - .gitignore and .claudeignore pattern handling
  - Local file discovery and filtering
  - Error handling decorators
- **Dependencies**: exceptions.py, provider_factory.py

#### exceptions.py
- **Primary Purpose**: Defines custom exceptions for the application
- **Key Functions**:
  - `ConfigurationError`: For issues with application configuration
  - `ProviderError`: For issues with provider operations
- **Dependencies**: None

### Package Files

#### __init__.py
- **Primary Purpose**: Marks the directory as a Python package
- **Key Functions**: None (empty file)
- **Dependencies**: None

## Subdirectories

### cli
This directory contains the command-line interface components of ClaudeSync. It implements the user-facing commands for authentication, project management, file operations, and synchronization.

Key features from the CLI README:
- Provides commands for authentication, configuration, and synchronization
- Implements project and organization management functionality
- Contains synchronization logic and file operations
- Uses Click library for command implementation
- Supports shell auto-completion for better user experience

### configmanager
This directory provides the configuration management infrastructure for ClaudeSync, handling both global and project-specific settings.

Key features from the ConfigManager README:
- Implements abstract and concrete configuration manager classes
- Manages global configuration in `~/.claudesync/config.json`
- Handles local project configurations in `.claudesync/` directories
- Provides session key management with secure encryption
- Implements hierarchical configuration with defaults

### providers
This directory contains the provider interfaces and implementations for communicating with Claude AI services.

Key features from the Providers README:
- Defines the abstract base class for all providers
- Implements Claude AI-specific provider functionality
- Handles authentication, data access, and API interactions
- Manages chat conversations, file operations, and projects
- Implements error handling for API responses

### web
This directory contains an Angular-based web interface for ClaudeSync, providing a graphical alternative to the CLI.

Key features from the Web README:
- Built with Angular CLI (version 19.0.2)
- Provides a development server with hot reloading
- Includes build tools and test runners
- Contains the frontend application code

## Usage Context

### When to Analyze Files in This Directory

- When investigating core synchronization logic issues
- When extending or modifying the synchronization process
- When implementing new provider integrations
- When troubleshooting authentication or configuration problems
- When optimizing file compression or token counting

### Common Questions or Tasks

1. How does file synchronization work between local and remote environments?
2. How are files compressed for efficient transfer?
3. How is authentication handled with Claude AI?
4. How are configuration settings managed across global and project levels?
5. How are tokens counted for Claude AI's context limits?

### Relationships with Other Components

- **CLI**: The core components are used by the CLI to provide command-line functionality
- **Web Interface**: The core components can be wrapped by the web interface for GUI access
- **External Services**: The providers directory handles communication with Claude AI services
- **Local Filesystem**: The synchronization logic interacts with the local filesystem

## Design Patterns and Architecture

1. **Factory Pattern**: Provider implementations are created through the provider_factory.py
2. **Strategy Pattern**: Multiple compression algorithms can be selected at runtime
3. **Decorator Pattern**: Error handling is implemented as a decorator in utils.py
4. **Repository Pattern**: Local and remote file repositories are synchronized
5. **Adapter Pattern**: Provider interfaces adapt external APIs to a consistent interface

## Configuration Files

- `.gitignore` and `.claudeignore`: Used to exclude files from synchronization
- Configuration files are managed through the ConfigManager in the configmanager directory
- Global config is stored in `~/.claudesync/config.json`
- Project config is stored in `.claudesync/config.json` within each project directory

## Special Notes

- The core synchronization process supports both one-way and two-way synchronization
- Files are compared using MD5 hashes to determine changes
- Token counting is implemented using the TikToken library with cl100k_base encoding
- Session keys are securely managed using SSH key-based encryption
- The system supports multiple compression algorithms for optimizing transfer sizes

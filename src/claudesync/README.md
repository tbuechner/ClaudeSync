# ClaudeSync Core

This directory contains the core components of the ClaudeSync application, which enables synchronization between local files and Claude AI projects.

## Overview

ClaudeSync is a tool designed to facilitate the synchronization of local files with Claude AI projects, enabling efficient AI-assisted development workflows. The core modules in this directory handle configuration management, file synchronization, provider integration, compression algorithms, and utility functions.

## Source Files

### Main Components

#### syncmanager.py
- **Primary Purpose**: Manages the synchronization process between local and remote files
- **Key Components**:
  - `SyncManager` class: Handles file uploads, downloads, and delta synchronization
  - `retry_on_403` decorator: Handles temporary API failures with retry logic
- **Key Functions**:
  - `sync()`: Main synchronization method that orchestrates the sync process
  - Implements both standard synchronization and compressed batch transfer
  - File comparison using MD5 hashes and timestamp-based updates
  - Support for two-way sync and remote file pruning
- **Dependencies**: compression.py, utils.py, exceptions.py

#### provider_factory.py
- **Primary Purpose**: Factory for creating provider instances
- **Key Functions**:
  - `get_provider()`: Returns an instance of the appropriate provider (currently ClaudeAIProvider)
- **Dependencies**: providers/claude_ai.py, providers/base_provider.py

#### compression.py
- **Primary Purpose**: Provides file compression algorithms for efficient file transfers
- **Key Components**:
  - Multiple compression implementations: zlib, bz2, lzma, brotli, dictionary, RLE, Huffman, and LZW
  - `HuffmanNode` class for Huffman coding implementation
- **Key Functions**:
  - `compress_files()` and `decompress_files()`: Pack and compress/decompress multiple files
  - `_pack_files()` and `_unpack_files()`: Bundle multiple files into a single content stream
  - Compression algorithm implementations with consistent interface
- **Dependencies**: Uses Python standard libraries for compression

#### token_counter.py
- **Primary Purpose**: Counts tokens in text content for Claude AI models
- **Key Components**:
  - `TokenCounter` class: Manages token counting with TikToken library
- **Key Functions**:
  - `count_tokens()`: Counts tokens in a string using cl100k_base encoding
  - `count_file_tokens()`: Counts tokens in a file
  - `count_project_tokens()`: Analyzes token usage across multiple project files
- **Dependencies**: tiktoken, utils.py

#### session_key_manager.py
- **Primary Purpose**: Manages and secures Claude AI session keys
- **Key Components**:
  - `SessionKeyManager` class: Handles encryption/decryption of session keys
- **Key Functions**:
  - `encrypt_session_key()`: Encrypts session keys for secure storage
  - `decrypt_session_key()`: Decrypts stored session keys
  - Key derivation from SSH keys (ed25519, ecdsa)
- **Dependencies**: cryptography library

#### utils.py
- **Primary Purpose**: Provides utility functions used throughout the codebase
- **Key Functions**:
  - `normalize_and_calculate_md5()`: Normalizes line endings and calculates checksums
  - `load_gitignore()` and `load_claudeignore()`: Parse ignore patterns
  - `is_text_file()`: Detects if a file is text or binary
  - `get_local_files()`: Discovers local files matching patterns with optimized traversal
  - `handle_errors()`: Decorator for consistent error handling
  - `validate_and_get_provider()`: Validates configuration and retrieves provider
- **Dependencies**: exceptions.py, provider_factory.py, pathspec

#### exceptions.py
- **Primary Purpose**: Defines custom exceptions for the application
- **Key Components**:
  - `ConfigurationError`: Exception for issues with application configuration
  - `ProviderError`: Exception for issues with provider operations
- **Dependencies**: None

### Package Files

#### __init__.py
- **Primary Purpose**: Marks the directory as a Python package
- **Key Functions**: None (empty file)
- **Dependencies**: None

## Subdirectories

### cli
This directory contains the command-line interface components of ClaudeSync, providing functionality for synchronizing local files with AI projects.

Key features:
- Main entry point for the ClaudeSync CLI application
- Authentication and configuration management
- Project and organization management
- File operations and synchronization commands
- Chat functionality and token counting
- Uses Click library for command implementation
- Supports shell auto-completion for better user experience

### configmanager
This directory provides the configuration management infrastructure for ClaudeSync, handling both global and project-specific settings.

Key features:
- Abstract base class (`BaseConfigManager`) defining the configuration interface
- File-based implementation (`FileConfigManager`) for JSON storage
- Global configuration in `~/.claudesync/config.json`
- Local project configurations in `.claudesync/` directories
- Session key management with encryption/decryption
- Hierarchical configuration with sensible defaults

### providers
This directory contains provider interfaces and implementations for communicating with Claude AI services.

Key features:
- Abstract base class (`BaseProvider`) defining the provider interface
- Base Claude AI implementation (`BaseClaudeAIProvider`) with common functionality
- Concrete implementation (`ClaudeAIProvider`) using HTTP requests
- Authentication, organization, and project management
- File operations and chat functionality
- Specialized error handling for API responses

### web
This directory contains an Angular-based web interface for ClaudeSync, providing a graphical alternative to the CLI.

Key features:
- Angular framework implementation (Angular 16+)
- Interactive file visualization with Plotly.js treemaps
- Monaco Editor integration for configuration editing
- Responsive design adapting to different screen sizes
- Reactive programming with RxJS
- SPA architecture for seamless user experience
- Development server and build tools

## Usage Context

### When to Analyze Files in This Directory

- When investigating core synchronization logic issues
- When extending or modifying the synchronization process
- When implementing new provider integrations
- When troubleshooting authentication or configuration problems
- When optimizing file compression or token counting

### Common Questions or Tasks This Directory Addresses

1. How does file synchronization work between local and remote environments?
2. How are files compressed for efficient transfer?
3. How is authentication handled with Claude AI?
4. How are configuration settings managed across global and project levels?
5. How are tokens counted for Claude AI's context limits?
6. How are file changes detected and synchronized?

### Relationships with Other Major Directories

- The `src/claudesync` directory is the core of the ClaudeSync application
- The `cli` directory provides command-line access to the functionality
- The `web` directory provides graphical access to the functionality
- The `configmanager` handles persistent configuration
- The `providers` directory manages communication with Claude AI services

## Design Patterns and Architectural Decisions

1. **Factory Pattern**: Provider implementations are created through the provider_factory.py
2. **Strategy Pattern**: Multiple compression algorithms can be selected at runtime
3. **Decorator Pattern**: Error handling is implemented as a decorator in utils.py
4. **Repository Pattern**: Local and remote file repositories are synchronized
5. **Adapter Pattern**: Provider interfaces adapt external APIs to a consistent interface
6. **Hierarchical Configuration**: Global and local configurations are cascaded
7. **Secure Credential Management**: Session keys are stored with encryption

## Important Coding Conventions

1. Comprehensive error handling with specialized exceptions
2. Extensive logging for debugging and monitoring
3. File operations with explicit UTF-8 encoding for cross-platform compatibility
4. Consistent interface patterns across provider implementations
5. Time-limited file traversal to prevent hanging on large directories
6. Secure handling of authentication credentials
7. Efficient file transfer with multiple compression algorithms

The ClaudeSync core provides a robust foundation for synchronizing local files with Claude AI projects, enabling efficient AI-assisted development workflows with both command-line and web interfaces.

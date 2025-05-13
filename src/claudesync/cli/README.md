# CLI Directory

The CLI directory contains the command-line interface components of ClaudeSync, providing functionality for synchronizing local files with AI projects. It implements the core user-facing commands and their respective subcommands for managing projects, files, authentication, and synchronization logic.

## Files in this Directory

### Main Components

#### main.py
- **Primary Purpose**: Serves as the entry point for the ClaudeSync CLI application
- **Key Components**: 
  - Main `cli` click group that bundles all commands
  - `install_completion` and `push` commands
  - Registration of all subcommands (auth, organization, project, etc.)
- **Dependencies**: Imports from all other CLI modules

#### __init__.py
- **Primary Purpose**: Makes the CLI directory a proper Python package
- **Key Components**: Exports the `cli` function from main.py
- **Dependencies**: main.py

### Authentication and Configuration

#### auth.py
- **Primary Purpose**: Manages user authentication with Claude AI
- **Key Components**: 
  - `login` command for authenticating with session keys
  - `logout` command for clearing session keys
  - `ls` command to list authenticated providers
- **Dependencies**: provider_factory, utils, exceptions

#### config.py
- **Primary Purpose**: Manages ClaudeSync configuration
- **Key Components**: 
  - `set` command for setting configuration values
  - `get` command for retrieving configuration values
  - `ls` command for listing all configurations
- **Dependencies**: exceptions, utils

### Project Management

#### project.py
- **Primary Purpose**: Manages AI projects within organizations
- **Key Components**: 
  - `create` command for creating new projects
  - `set` command for setting the active project
  - `archive` command for archiving projects
  - `ls` command to list all configured projects
  - Helper functions for managing .gitignore entries and project templates
- **Dependencies**: provider_factory, utils, exceptions, file.py, syncmanager

#### organization.py
- **Primary Purpose**: Manages organization-related operations
- **Key Components**: Commands for working with Claude AI organizations
- **Dependencies**: provider_factory, utils, exceptions

### File and Synchronization

#### file.py
- **Primary Purpose**: Manages file operations for projects
- **Key Components**: Commands for adding, removing, and listing files
- **Dependencies**: utils, exceptions

#### sync.py
- **Primary Purpose**: Contains commands for synchronization operations
- **Key Components**: 
  - `ls` command to list files in remote projects
  - Utility functions for validating local paths
- **Dependencies**: utils, exceptions

#### sync_logic.py
- **Primary Purpose**: Implements the core synchronization logic
- **Key Components**: 
  - `push_files` function for pushing files to Claude.ai
  - Handles project configuration, file discovery, and synchronization
- **Dependencies**: utils, exceptions, configmanager, syncmanager

#### zip.py
- **Primary Purpose**: Handles project archive/compression operations
- **Key Components**: Commands for zipping project files
- **Dependencies**: utils, exceptions

### Additional Functionality

#### chat.py
- **Primary Purpose**: Manages chat conversations with Claude AI
- **Key Components**: 
  - `init` command for initializing new chat conversations
  - `message` command for sending messages to chats
  - Helper functions for selecting projects and creating chats
- **Dependencies**: exceptions, utils

#### export.py
- **Primary Purpose**: Handles exporting data from Claude AI
- **Key Components**: Commands for exporting conversations and projects
- **Dependencies**: utils, exceptions

#### simulate.py
- **Primary Purpose**: Provides simulation functionality for testing
- **Key Components**: `simulate_push` command for testing file synchronization
- **Dependencies**: utils, exceptions, sync_logic

#### tokens.py
- **Primary Purpose**: Manages token counting and quotas
- **Key Components**: Commands for checking token usage and limits
- **Dependencies**: utils, exceptions

## Subdirectories

### __pycache__
- Contains Python bytecode files for the CLI modules
- Generated automatically by Python, should not be manually modified

## Usage Context

### When to Analyze Files in this Directory

- When investigating issues with the command-line interface
- When extending or modifying CLI commands
- When troubleshooting synchronization or authentication problems
- When understanding the flow of operations in ClaudeSync

### Common Questions This Directory Addresses

1. How does ClaudeSync authenticate with Claude AI?
2. How are files synchronized between local and remote projects?
3. How are projects created and managed?
4. How does the command structure work in the CLI?
5. How does configuration management work?

### Relationships with Other Major Directories

- **claudesync/configmanager**: The CLI uses the configuration management to persist settings and project information
- **claudesync/providers**: The CLI commands interact with AI providers through the provider interfaces
- **claudesync/web**: The CLI provides command-line access to the same functionality available in the web interface
- **claudesync/syncmanager**: The CLI delegates actual synchronization logic to this component

## Design Patterns and Architectural Decisions

1. **Command Pattern**: Uses Click library to implement nested command groups with a consistent interface
2. **Factory Pattern**: Uses provider_factory to instantiate the appropriate provider implementation
3. **Error Handling**: Consistent error handling through the `handle_errors` decorator
4. **Configuration Management**: Separates global and project-specific configuration
5. **Project Structure**: Organizes projects with nested configurations in the .claudesync directory
6. **Command Organization**: Commands are grouped by functional area (auth, project, file, etc.)
7. **Auto-completion**: Supports shell auto-completion for better user experience

This directory is the main entry point for users interacting with ClaudeSync through the command line, providing a comprehensive set of tools for managing files and projects with Claude AI.

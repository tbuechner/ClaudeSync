# ClaudeSync Project Structure

This project, "ClaudeSync - FE", focuses on the frontend aspects of a system called ClaudeSync, which appears to be a tool for synchronizing files with Claude AI. The project includes the following components:

## Backend Python Files
- `src/claudesync/cli/simulate.py`: A Python module providing simulation functionality for the CLI, including HTTP server implementation that powers the web frontend's API
- `src/claudesync/utils.py`: Utility functions for file handling, path processing, MD5 hash calculation, and pattern matching against .gitignore and .claudeignore files

## Frontend Configuration
- `src/claudesync/web/package.json`: NPM dependencies and scripts configuration
- `src/claudesync/web/angular.json`: Angular project configuration and build settings
- `src/claudesync/web/tsconfig.json`: TypeScript compiler options and configuration

## Frontend Source Code
- `src/claudesync/web/src/**`: All files in the Angular application source directory, including:
  - Components for visualization (treemap, file preview, modal dialogs)
  - Service files for data handling and API communication
  - HTML templates and CSS files for UI components
  - Core application files (app.component, app.routes, etc.)

The application appears to be a visualization tool for ClaudeSync that displays which files would be synchronized with Claude AI, allows configuration editing, and provides simulation capabilities for file synchronization.
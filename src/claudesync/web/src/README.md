# ClaudeSync Web Application Source

This directory contains the core source code for the ClaudeSync web application, which provides a visual interface for synchronizing local project files with Claude AI. It contains the main entry points and the Angular application structure.

## Source Files

### index.html
- **Primary Purpose**: Main HTML entry point for the web application
- **Key Components**: 
  - Sets up the document structure and metadata
  - Loads external dependencies (Plotly.js for treemap visualization)
  - Contains the app-root element where the Angular application is bootstrapped

### main.ts
- **Primary Purpose**: Angular application bootstrap file
- **Key Functions**: 
  - Bootstraps the main AppComponent using Angular's standalone component architecture
  - Applies application configuration from app.config.ts
  - Sets up error handling for bootstrap failures

### styles.css
- **Primary Purpose**: Global CSS styles for the application
- **Key Features**:
  - Defines base typography using a system font stack
  - Provides a foundation for component-specific styles

## Subdirectories

### app/
This directory contains the core components, services, and utilities for the ClaudeSync web application.

**Summary of app/README.md**: 
The app directory is the heart of the ClaudeSync web application, containing components for treemap visualization, file management, project selection, and configuration editing. Key components include:
- **Core Application Files**: app.component, app.config.ts, app.routes.ts
- **Visualization Components**: treemap.component, file-preview.component
- **UI Components**: project-dropdown.component, drop-zone.component, modal.component, toast-notifications.component
- **Services**: file-data.service.ts (API interaction), loading.service.ts, notification.service.ts

The application follows Angular's standalone component architecture, uses reactive programming with RxJS, and implements patterns like service-based architecture, caching strategies, and responsive design. It includes features like drag-and-drop file selection, modal-based workflows, and comprehensive error handling.

## Usage Context

### When to Analyze Files in This Directory
- When investigating the main entry points of the ClaudeSync web application
- When troubleshooting application bootstrap issues
- When examining global styles and external dependencies
- When understanding the overall structure of the Angular application

### Common Questions or Tasks This Directory Addresses
- How is the ClaudeSync web application bootstrapped?
- What external dependencies are required for the application?
- How is the base HTML structure organized?
- What global styles are applied across the application?

### Relationships with Other Major Directories
This directory serves as the root of the ClaudeSync web application source code:

1. **/src/claudesync/web**: Parent directory containing build configuration, package management, and other web-related files
2. **/src/claudesync/api**: Backend API that this web application interacts with to retrieve project data and manage file synchronization
3. **/src/claudesync/cli**: Command-line interface that provides similar functionality to this web application but in a CLI context

The web application provides a visual interface to the same synchronization capabilities available through the CLI, using the shared backend API for data processing and file management.

## Configuration and Special Files

### Angular Implicit Dependencies
While not explicitly listed in this directory, the application relies on Angular's core modules and libraries, which are configured in the app.config.ts file within the app/ subdirectory.

### External Dependencies
- **Plotly.js**: Loaded in index.html for treemap visualization functionality

## Design Patterns and Architectural Decisions

1. **Angular Standalone Component Architecture**: The application is bootstrapped using Angular's standalone component architecture, reducing dependency on NgModules.

2. **Single Page Application**: The application is designed as a single page application with all functionality contained within a single view.

3. **External Visualization Library**: The decision to use Plotly.js for treemap visualization over building a custom visualization solution.

4. **Minimal Global Styling**: Global styles are kept minimal, with component-specific styling applied at the component level.

5. **Error Handling at Bootstrap**: Bootstrap errors are caught and logged to console, providing a foundation for application-wide error handling.

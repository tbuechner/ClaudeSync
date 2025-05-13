# ClaudeSync Web Application

This directory contains the web-based user interface for ClaudeSync, an application that facilitates synchronization of local project files with Claude AI. It provides a visual interface for project file selection, visualization, and configuration management.

## Source Code Files

### Configuration Files
- **angular.json** - Angular CLI configuration defining build options, assets, and environments
- **tsconfig.json** - TypeScript compiler configuration for the project
- **tsconfig.app.json** - TypeScript configuration specific to the application
- **tsconfig.spec.json** - TypeScript configuration for testing
- **package.json** - NPM package definition with dependencies and scripts
- **package-lock.json** - Locked versions of dependencies for consistent installations
- **.editorconfig** - Editor configuration for consistent code formatting
- **.gitignore** - Git ignore rules for the project
- **.tool-versions** - Defines tool versions for asdf version manager

## Subdirectories

### /src
The core source code directory for the ClaudeSync web application.

**Summary of src/README.md**: 
Contains the main entry points for the Angular application and global styles. Key files include `index.html` (HTML entry point), `main.ts` (Angular bootstrap), and `styles.css` (global styles). It uses Plotly.js for treemap visualization and implements Angular's standalone component architecture. The directory is the root of the ClaudeSync web application source, providing a visual interface to the synchronization capabilities.

### /src/app
The heart of the ClaudeSync web application's functionality.

**Summary of app/README.md**:
This directory contains all components, services, and utilities for the application. It includes visualization components (treemap, file-preview), UI components (project-dropdown, drop-zone, modal), and services for API interaction (file-data.service). The application implements patterns like service-based architecture, reactive programming with RxJS, caching strategies, and responsive design. It features drag-and-drop file selection, interactive treemap visualization, modal-based workflows, and comprehensive error handling.

### /public
Contains static assets for the web application:
- **favicon.ico** - Application favicon displayed in browser tabs

### /dist
Build output directory for the compiled application.

### /node_modules
Contains all installed NPM dependencies (not version controlled).

### /.angular
Contains Angular CLI cache and workspace data (not version controlled).

### /.vscode
Contains Visual Studio Code workspace settings (optional, may be version controlled).

## Usage Context

### When to Analyze Files in This Directory
- When setting up the ClaudeSync web development environment
- When configuring the Angular build process
- When managing dependencies for the web application
- When deploying the web application to production environments
- When updating Angular or TypeScript configurations

### Common Questions or Tasks This Directory Addresses
- How is the ClaudeSync web application built and deployed?
- What dependencies are required for development and production?
- How is the Angular application configured?
- What development scripts are available for testing and building?

### Relationships with Other Major Directories
This web directory represents the frontend component of the ClaudeSync application. The web application serves as the visual interface to the same synchronization capabilities provided by the CLI, using the shared backend API for data processing and file synchronization with Claude AI.

## Key Design Patterns and Architectural Decisions

1. **Angular Framework**: The application is built using Angular 16, utilizing its standalone component architecture for improved modularity.

2. **Interactive Visualization**: Employs Plotly.js for rich treemap visualization of project files, allowing intuitive size-based visualization and selection.

3. **Monaco Editor Integration**: Uses Monaco Editor (the editor powering VS Code) for configuration file editing with syntax highlighting.

4. **Responsive Design**: The UI adapts to different screen sizes while maintaining rich visualization capabilities.

5. **Reactive Programming**: Utilizes RxJS (version 6.6.7) for reactive programming paradigms and handling asynchronous operations.

6. **SPA Architecture**: Implemented as a Single Page Application for seamless user experience without page reloads.

7. **Build Process**: Uses Angular CLI for standardized build processes, including production optimization.

## Development

### Development Server
```bash
ng serve
```
Navigate to `http://localhost:4200/`. The application automatically reloads on source changes.

### Building for Production
```bash
ng build
```
Build artifacts will be stored in the `dist/` directory.

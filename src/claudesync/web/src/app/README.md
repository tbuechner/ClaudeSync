# ClaudeSync Web Application Core

This directory contains the core components, services, and utilities for the ClaudeSync web application, which facilitates file synchronization between local projects and Claude AI.

## Source Files

### Main Application Files

- **app.component.ts/html/css**: Root component that manages the overall application layout, project selection, and configuration display.
  - Integrates the treemap visualization, project dropdown, toast notifications, and configuration editors
  - Handles project loading, data refreshing, and pushing files to Claude
  - Dependencies: FileDataService, NotificationService, TreemapComponent, ProjectDropdownComponent

- **app.config.ts**: Angular application configuration with provider setup.

- **app.routes.ts**: Defines application routes (currently an empty array as this is a single-page application).

### Components

- **treemap.component.ts/html/css**: Core visualization component that displays project files in a treemap format.
  - Renders interactive treemap of files showing size and inclusion status
  - Handles file/folder selection, hiding folders, and file preview features
  - Dependencies: FileDataService, NotificationService

- **treemap.types.ts**: TypeScript interfaces for the treemap component.
  - Defines TreemapData, TreeNode, FileInfo, and SelectedNode interfaces

- **project-dropdown.component.ts/html/css**: Dropdown menu for selecting projects.
  - Displays list of available projects
  - Emits events when a project is selected

- **file-preview.component.ts/html/css**: Modal component for previewing file content.
  - Displays file content with syntax highlighting
  - Handles various file types with appropriate formatting

- **modal.component.ts/html/css**: Reusable modal dialog component.
  - Provides a customizable modal dialog with backdrop
  - Used by other components to display content in an overlay

- **node-actions-menu.component.ts/html/css**: Context menu for file/folder operations.
  - Provides actions like copying paths, including/excluding files, hiding folders
  - Integrates with the treemap component

- **drop-zone.component.ts/html/css**: Component for drag-and-drop file upload functionality.
  - Allows users to drop files to resolve them against the project
  - Integrated with treemap for visualizing dropped files

- **toast-notifications.component.ts/html/css**: Notification system for user feedback.
  - Displays success, error, warning, and info messages
  - Auto-dismisses notifications after a configured timeout

- **editable-config.component.ts/css**: Component for editing configuration files.
  - Provides code editor functionality for project configuration and .claudeignore files
  - Features syntax highlighting and validation

- **global-loading.component.ts**: Loading indicator component for asynchronous operations.
  - Displays a full-screen loading spinner during API calls
  - Controlled by the LoadingService

### Services

- **file-data.service.ts**: Core service for interacting with the backend API.
  - Fetches project data, file content, and synchronization status
  - Handles caching of data for performance optimization
  - Provides methods for pushing files, updating configuration, and resolving dropped files

- **loading.service.ts**: Service for managing loading state during API calls.
  - Tracks active loading operations
  - Used to show/hide the global loading indicator

- **notification.service.ts**: Service for managing toast notifications.
  - Provides methods for displaying success, error, warning, and info messages
  - Controls notification timeouts and display queue

## Usage Context

### When to Analyze Files in This Directory

- When investigating the web UI functionality of the ClaudeSync application
- When troubleshooting issues with file synchronization visualization or configuration
- When implementing new features for the ClaudeSync web interface
- When modifying how files are selected, filtered, or displayed in the application

### Common Questions This Directory Addresses

- How are project files visualized in the treemap?
- How does the application determine which files to include/exclude in synchronization?
- How are project configurations and .claudeignore files edited and saved?
- How does the UI handle large projects with many files, including timeout scenarios?
- How do users interact with the file selection and synchronization process?

### Relationships with Other Major Directories

This directory contains the frontend Angular application for ClaudeSync, which communicates with a backend API to:

1. Retrieve project data and file information
2. Push selected files to Claude
3. Manage project configuration settings

The web application visualizes and manages the same data that the CLI component works with, providing a graphical interface for the ClaudeSync functionality.

## Design Patterns and Architectural Decisions

1. **Angular Standalone Components**: The application uses Angular's standalone component architecture, making components more self-contained and easier to maintain.

2. **Reactive Programming**: Extensive use of RxJS Observables for handling asynchronous operations and data flow.

3. **Service-Based Architecture**: Core functionality is abstracted into services (FileDataService, LoadingService, NotificationService) that can be injected into components.

4. **Data Visualization**: Uses Plotly.js for interactive treemap visualization of project files.

5. **Caching Strategy**: The FileDataService implements caching to improve performance and reduce unnecessary API calls.

6. **Error Handling**: Comprehensive error handling with user-friendly notifications for all API interactions.

7. **Responsive Design**: The UI adapts to different screen sizes while providing rich visualization capabilities.

8. **Timeout Handling**: Special handling for large projects that might time out during file traversal, with appropriate UI feedback.

9. **Drag and Drop Integration**: Native browser drag and drop API integration for file selection.

10. **Modal-Based Workflows**: Uses modal dialogs for focused tasks like file preview and configuration editing.

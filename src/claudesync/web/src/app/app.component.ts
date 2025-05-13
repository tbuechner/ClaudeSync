import {Component, OnInit, ViewChild} from '@angular/core';
import {CommonModule} from '@angular/common';
import {HttpClientModule} from '@angular/common/http';
import {FileDataService, ProjectConfig, SyncData, SyncStats} from './file-data.service';
import {TreemapComponent} from './treemap.component';
import {Project, ProjectDropdownComponent} from './project-dropdown.component';
import {NotificationService} from './notification.service'
import {ToastNotificationsComponent} from './toast-notifications.component';
import {EditableConfigComponent} from './editable-config.component';
import {GlobalLoadingComponent} from './global-loading.component';



@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    HttpClientModule,
    TreemapComponent,
    ProjectDropdownComponent,
    ToastNotificationsComponent,
    EditableConfigComponent,
    GlobalLoadingComponent
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
  providers: [FileDataService]
})
export class AppComponent implements OnInit {
  isTreemapViewModified = false;
  configVisible = false;
  claudeignore = '';
  stats: SyncStats = {
    filesToSync: 0,
    totalSize: '0 B'
  };

  syncData: SyncData | null = null;
  timeoutOccurred = false;
  timeoutMessage = '';

  projects: Project[] = [];
  selectedProject: string = '';
  selectedProjectUrl: string = '';
  projectConfig: ProjectConfig | null = null;

  @ViewChild(TreemapComponent) treemapComponent!: TreemapComponent;

  constructor(private fileDataService: FileDataService,
              private notificationService: NotificationService) {
  }

  ngOnInit() {
    this.loadProjects();
  }

  /**
   * Checks if the treemap view has been modified
   * Used to update the Reload button appearance
   * @returns True if the treemap view has been modified (folders hidden or reloaded)
   */
  checkTreemapViewModified(): boolean {
    // Cache the result to avoid repeatedly accessing the view component
    if (this.treemapComponent && typeof this.treemapComponent.viewIsModified !== 'undefined') {
      this.isTreemapViewModified = this.treemapComponent.viewIsModified;
    }
    return this.isTreemapViewModified;
  }

  loadProjects() {
    this.fileDataService.getProjects()
      .subscribe({
        next: (response: any) => {
          this.projects = response.projects.sort((a: any, b: any) => a.path.localeCompare(b.path));
          if (response.activeProject) {
            this.selectedProject = response.activeProject;
            this.setSelectedProjectUrl();
            this.loadData();
          } else if (this.projects.length > 0) {
            // If no active project but projects exist, select the first one
            this.selectedProject = this.projects[0].path;
            this.setSelectedProjectUrl();
            this.onProjectChange(this.projects[0].path);
          }
        },
        error: (error) => {
          console.error('Error loading projects:', error);
          this.notificationService.error('Failed to load projects. Please try again.');
        }
      });
  }

  onProjectChange(projectPath: string) {
    this.selectedProject = projectPath;
    this.setSelectedProjectUrl();

    // Clear the current data before loading new project
    this.fileDataService.clearCache();

    // Clear the treemap by setting syncData to null
    this.syncData = null;

    // Reset stats
    this.stats = {
      filesToSync: 0,
      totalSize: '0 B'
    };

    // Reset timeout state when changing projects
    this.timeoutOccurred = false;
    this.timeoutMessage = '';

    this.fileDataService.setActiveProject(projectPath)
      .subscribe({
        next: () => {
          // After setting the project, trigger a full reload
          this.reload();
        },
        error: (error) => {
          console.error('Error setting active project:', error);
          this.notificationService.error('Failed to set active project. Please try again.');
        }
      });
  }

  private setSelectedProjectUrl() {
    // Find the project ID from the projects array and set the URL
    const project = this.projects.find(p => p.path === this.selectedProject);
    if (project) {
      this.selectedProjectUrl = `https://claude.ai/project/${project.id}`;
    } else {
      this.selectedProjectUrl = '';
    }
  }

  loadData() {
    this.fileDataService.getSyncData()
      .subscribe({
        next: (data) => {
          this.syncData = data;
          this.projectConfig = data.project;
          this.claudeignore = data.claudeignore;
          this.stats = data.stats;

          // Handle timeout condition
          if (data.timeout) {
            this.timeoutOccurred = true;
            this.timeoutMessage = data.timeoutMessage || 'File traversal timed out. Your project may have too many files to process.';
            this.notificationService.warning(this.timeoutMessage);
          } else {
            this.timeoutOccurred = false;
            this.timeoutMessage = '';
          }
        },
        error: (error) => {
          console.error('Error loading data:', error);
          this.notificationService.error('Failed to load project data. Please try again.');
        }
      });
  }

  toggleConfig() {
    this.configVisible = !this.configVisible;
  }

  reload() {
    this.fileDataService.refreshCache()
      .subscribe({
        next: (data) => {
          // Create a new object reference to trigger change detection
          this.syncData = {...data};  // Use spread to create a new reference
          this.projectConfig = data.project;
          this.claudeignore = data.claudeignore;
          this.stats = data.stats;

          // Reset the treemap view modified state
          this.isTreemapViewModified = false;

          // Force button state to update by explicitly calling checkTreemapViewModified
          this.checkTreemapViewModified();

          // Handle timeout condition
          if (data.timeout) {
            this.timeoutOccurred = true;
            this.timeoutMessage = data.timeoutMessage || 'File traversal timed out. Your project may have too many files to process.';
            this.notificationService.warning(this.timeoutMessage);
          } else {
            this.timeoutOccurred = false;
            this.timeoutMessage = '';
          }
        },
        error: (error) => {
          console.error('Error loading data:', error);
          this.notificationService.error('Failed to reload project data. Please try again.');
        }
      });
  }

  getProjectConfigAsJson(): string {
    return this.projectConfig
      ? JSON.stringify(this.projectConfig, null, 2)
      : '{}';
  }

  push() {
    // If timeout occurred, confirm before pushing
    if (this.timeoutOccurred) {
      if (!confirm('File traversal timed out, which means not all files may be included. Do you still want to push?')) {
        return;
      }
    }

    this.fileDataService.push()
      .subscribe({
        next: (response) => {
          // Show success notification with the response message
          if (response && response.message) {
            this.notificationService.success(response.message);
          } else {
            this.notificationService.success('Files pushed successfully!');
          }
          this.reload();
        },
        error: (error) => {
          // Show error notification with the error message
          const errorMessage = error.error?.message || 'Failed to push files. Please try again.';
          this.notificationService.error(errorMessage);
          console.error('Error pushing to backend:', error);
        }
      });
  }

  saveProjectConfig(newContent: string) {
    console.debug('Saving project config', newContent.substring(0, 100) + '...');

    this.fileDataService.saveProjectConfig(newContent)
      .subscribe({
        next: () => {
          // Update the local project config
          try {
            this.projectConfig = JSON.parse(newContent);
            this.notificationService.success('Project configuration updated successfully');
            // Trigger a reload to refresh the view
            this.reload();

            // Additional line to ensure treemap gets refreshed
            if (this.treemapComponent) {
              setTimeout(() => this.treemapComponent.updateTreemap(), 100);
            }
          } catch (error) {
            this.notificationService.error('Error parsing updated configuration');
            console.error('JSON parse error:', error);
          }
        },
        error: (error) => {
          // More specific error messages based on status codes
          if (error.status === 400) {
            this.notificationService.error(error.error?.error || 'Invalid configuration format');
          } else if (error.status === 403) {
            this.notificationService.error('Permission denied when saving configuration');
          } else {
            this.notificationService.error('Failed to save project configuration');
          }
          console.error('Configuration save error:', error);
        }
      });
  }

  saveClaudeIgnore(newContent: string) {
    console.debug('Saving project config', newContent.substring(0, 100) + '...');

    this.fileDataService.saveClaudeIgnore(newContent)
      .subscribe({
        next: () => {
          this.claudeignore = newContent;
          this.notificationService.success('.claudeignore updated successfully');
          // Trigger a reload to refresh the view
          this.reload();
        },
        error: (error) => {
          // More specific error messages based on status codes
          if (error.status === 400) {
            this.notificationService.error(error.error?.error || 'Invalid .claudeignore format');
          } else if (error.status === 403) {
            this.notificationService.error('Permission denied when saving .claudeignore');
          } else {
            this.notificationService.error('Failed to save .claudeignore');
          }
          console.error('Claudeignore save error:', error);
        }
      });
  }
}

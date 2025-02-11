import {Component, OnInit, ViewChild} from '@angular/core';
import {CommonModule} from '@angular/common';
import {HttpClientModule} from '@angular/common/http';
import {FileDataService, ProjectConfig, SyncData, SyncStats} from './file-data.service';
import {TreemapComponent} from './treemap.component';
import {finalize} from 'rxjs/operators';
import {Project, ProjectDropdownComponent} from './project-dropdown.component';
import {NotificationService} from './notification.service'
import {ToastNotificationsComponent} from './toast-notifications.component';


@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, HttpClientModule, TreemapComponent, ProjectDropdownComponent, ToastNotificationsComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
  providers: [FileDataService]
})
export class AppComponent implements OnInit {
  configVisible = false;
  claudeignore = '';
  isLoading = false;
  stats: SyncStats = {
    filesToSync: 0,
    totalSize: '0 B'
  };

  syncData: SyncData | null = null;

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

  loadProjects() {
    this.isLoading = true;
    this.fileDataService.getProjects()
      .pipe(finalize(() => this.isLoading = false))
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
        }
      });
  }

  onProjectChange(projectPath: string) {
    this.selectedProject = projectPath;
    this.isLoading = true;

    this.setSelectedProjectUrl();

    // Clear the current data before loading new project
    this.fileDataService.clearCache();

    this.fileDataService.setActiveProject(projectPath)
      .subscribe({
        next: () => {
          // After setting the project, trigger a full reload
          this.reload();
        },
        error: (error) => {
          console.error('Error setting active project:', error);
          this.isLoading = false;
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
    this.isLoading = true;
    this.fileDataService.getSyncData()
      .subscribe({
        next: (data) => {
          this.syncData = data;
          this.projectConfig = data.project;
          this.claudeignore = data.claudeignore;
          this.stats = data.stats;
          this.isLoading = false;
        },
        error: (error) => {
          console.error('Error loading data:', error);
          this.isLoading = false;
        }
      });
  }

  toggleConfig() {
    this.configVisible = !this.configVisible;
  }

  reload() {
    this.isLoading = true;
    this.fileDataService.refreshCache()
      .subscribe({
        next: (data) => {
          this.syncData = data;
          this.projectConfig = data.project;
          this.claudeignore = data.claudeignore;
          this.stats = data.stats;
          this.isLoading = false;
        },
        error: (error) => {
          console.error('Error loading data:', error);
          this.isLoading = false;
        }
      });
  }

  getProjectConfigAsJson() {
    return this.projectConfig ? JSON.stringify(this.projectConfig, null, 2) : '';
  }

  push() {
    this.isLoading = true;
    this.fileDataService.push()
      .pipe(finalize(() => this.isLoading = false))
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
}

import {Injectable} from '@angular/core';
import {HttpClient, HttpParams} from '@angular/common/http';
import {Observable, of} from 'rxjs';
import {map, tap} from 'rxjs/operators';
import {Project} from './project-dropdown.component';
import {LoadingService} from './loading.service';
import {DroppedFile} from './drop-zone.component';

export interface SyncStats {
  filesToSync: number;
  totalSize: string;
}

export interface ProjectConfig {
  name: string;
  description: string;
  includes: string[];
  excludes: string[];
}

export interface TreemapData {
  labels: string[];
  parents: string[];
  values: number[];
  ids: string[];
}

export interface FileContentResponse {
  content: string;
  error?: string;
}

export interface SyncData {
  claudeignore: string;
  project: ProjectConfig;
  stats: SyncStats;
  treemap: any;
  timeout?: boolean;         // Indicates if the operation timed out
  timeoutMessage?: string;   // Message explaining the timeout
}

@Injectable({
  providedIn: 'root'
})
export class FileDataService {
  private baseUrl = 'http://localhost:4201/api';
  private cachedData: SyncData | null = null;

  constructor(private http: HttpClient, private loadingService: LoadingService) {}

  private getSyncDataFromApi(): Observable<SyncData> {
    return this.loadingService.withLoading(
      this.http.get<SyncData>(`${this.baseUrl}/sync-data`, {}).pipe(
        tap(data => {
          this.cachedData = data;
          console.debug('Cached sync data updated');
        })
      ));
  }

  getSyncData(): Observable<SyncData> {
    if (this.cachedData) {
      return of(this.cachedData);
    }
    return this.getSyncDataFromApi();
  }

  getStats(): Observable<SyncStats> {
    return this.getSyncData().pipe(
      map(data => data.stats)
    );
  }

  refreshCache(): Observable<SyncData> {
    this.clearCache();
    return this.getSyncData();
  }

  clearCache(): void {
    this.cachedData = null;
    console.debug('Cache cleared');
  }

  getFileContent(filePath: string): Observable<FileContentResponse> {
    return this.loadingService.withLoading(
      this.http.get<FileContentResponse>(`${this.baseUrl}/file-content`, {
        params: { path: filePath }
      })
    );
  }

  getProjects(): Observable<Project[]> {
    return this.loadingService.withLoading(
      this.http.get<Project[]>(`${this.baseUrl}/projects`)
    );
  }

  setActiveProject(projectPath: string): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/set-active-project`, { path: projectPath }).pipe(
        tap(() => this.clearCache())
      )
    );
  }

  updateConfigIncrementally(config: { action: string, pattern: string }): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/update-config-incrementally`, config)
    );
  }

  push(): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/push`, {})
    );
  }

  /**
   * Saves project configuration changes to the backend
   * @param content The updated project configuration JSON string
   * @returns Observable of the API response
   */
  saveProjectConfig(content: string): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/replace-project-config`, { content }).pipe(
        tap(() => this.clearCache())
      )
    );
  }

  /**
   * Saves .claudeignore changes to the backend
   * @param content The updated .claudeignore content
   * @returns Observable of the API response
   */
  saveClaudeIgnore(content: string): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/save-claudeignore`, { content }).pipe(
        tap(() => this.clearCache())
      )
    );
  }

  resolveDroppedFiles(files: DroppedFile[]): Observable<any> {
    return this.loadingService.withLoading(
      this.http.post(`${this.baseUrl}/resolve-dropped-files`, { files })
    );
  }

  /**
   * Get all files in a folder, including those not included in the sync
   * @param folderPath Path to the folder relative to project root
   * @returns Observable of the folder contents with inclusion status
   */
  getFolderContents(folderPath: string): Observable<any> {
    return this.loadingService.withLoading(
      this.http.get(`${this.baseUrl}/folder-contents`, {
        params: { path: folderPath }
      })
    );
  }
}

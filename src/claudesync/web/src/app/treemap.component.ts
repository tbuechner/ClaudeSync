import {Component, Input, OnDestroy} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FileContentResponse, FileDataService, SyncData} from './file-data.service';
import {HttpClient} from '@angular/common/http';
import {FileInfo, SelectedNode, TreemapData, TreeNode} from './treemap.types';
import {FormsModule} from '@angular/forms';
import {FilePreviewComponent} from './file-preview.component';
import {ModalComponent} from './modal.component';
import {Subject, Subscription} from 'rxjs';

declare const Plotly: any;

@Component({
  selector: 'app-treemap',
  standalone: true,
  imports: [CommonModule, FormsModule, FilePreviewComponent, ModalComponent],
  templateUrl: './treemap.component.html',
  styleUrls: ['./treemap.component.css']
})
export class TreemapComponent implements OnDestroy {
  selectedNode: SelectedNode | null = null;
  showOnlyIncluded = false;
  isLoading = false;
  showFileList = false;
  private destroy$ = new Subject<void>();
  private baseUrl = 'http://localhost:4201/api';

  selectedFile: FileInfo | null = null;
  fileContent: string | null = null;
  fileContentError: string | null = null;
  isLoadingContent = false;

  private originalTreeData: any = null;
  private nodeMap = new Map<string, TreeNode>();

  files: FileInfo[] = [];
  private fileNodeMap = new Map<string, FileInfo>();

  filterText = '';

  private currentSubscription?: Subscription;

  @Input() set syncData(data: SyncData | null) {
    if (data) {
      this.originalTreeData = data.treemap;
      this.updateTreemap();
      this.updateFilesList(data.treemap);
    }
  }

  constructor(private http: HttpClient, private fileDataService: FileDataService) {
  }

  ngOnDestroy() {
    this.currentSubscription?.unsubscribe();
    this.destroy$.next();
    this.destroy$.complete();

    // Clean up Plotly events
    const chartContainer = document.getElementById('file-treemap');
    if (chartContainer) {
      Plotly.purge(chartContainer);
    }
  }

  private filterTree(node: any): any {
    if (!this.showOnlyIncluded) {
      return node;
    }

    if (!node.children) {
      // Leaf node (file)
      return node.included ? node : null;
    }

    // Filter children recursively
    const filteredChildren = (node.children || [])
      // @ts-ignore
      .map(child => this.filterTree(child))
      // @ts-ignore
      .filter(child => child !== null);

    if (filteredChildren.length === 0) {
      return null;
    }

    return {
      ...node,
      children: filteredChildren
    };
  }

  private updateTreemap() {
    if (!this.originalTreeData) return;

    const filteredData = this.filterTree(this.originalTreeData);
    if (filteredData) {
      this.renderTreemap(filteredData);
    }
  }

  private countFiles(node: TreeNode): number {
    if (!node.children?.length) {
      return 1;
    }
    return node.children.reduce((sum, child) => sum + this.countFiles(child), 0);
  }

  private formatSizeForHover(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  }

  private updateFilesList(treeData: any) {
    const files: FileInfo[] = [];
    this.fileNodeMap.clear();

    const processNode = (node: any, parentPath: string = '') => {
      const currentPath = parentPath ? `${parentPath}/${node.name}` : node.name;

      if ('size' in node) {
        // This is a file node
        const pathParts = currentPath.split('/');
        const fileName = pathParts.pop() || '';
        const filePath = pathParts.join('/');

        const fileInfo: FileInfo = {
          name: fileName,
          path: filePath,
          fullPath: currentPath,
          size: node.size,
          included: node.included
        };

        files.push(fileInfo);
        this.fileNodeMap.set(currentPath, fileInfo);
      } else if (node.children) {
        // Process all children of this directory
        node.children.forEach((child: any) => processNode(child, currentPath));
      }
    };

    processNode(treeData);
    this.files = files.sort((a, b) => a.fullPath.localeCompare(b.fullPath));
  }

  public loadTreemapData() {
    this.currentSubscription?.unsubscribe();
    this.isLoading = true;

    this.currentSubscription = this.fileDataService.getSyncData()
      .subscribe({
        next: (data) => {
          this.originalTreeData = data.treemap;
          this.updateTreemap();
          this.updateFilesList(data.treemap);
          this.isLoading = false;
        },
        error: (error) => {
          console.error('Error loading treemap data:', error);
          this.isLoading = false;
        }
      });
  }

  private renderTreemap(data: any) {
    const chartContainer = document.getElementById('file-treemap');
    if (!chartContainer) {
      console.warn('Chart container not found');
      return;
    }

    const plotlyData = this.flattenTree(data);

    // Create color array based on node paths
    const colors = plotlyData.ids.map((id, index) => {
      const path = id.split('/');
      const isIncluded = plotlyData.included[index];

      // If not included (excluded), always use gray
      if (!isIncluded) {
        return '#e5e7eb';  // A lighter gray for excluded items
      }

      // Root level
      if (path.length === 1 && path[0] === 'root') {
        return '#f8fafc';  // Light gray for root
      }

      // Main project section
      if (path[1] === 'main') {
        if (path.length === 2) {
          return '#818cf8';  // Light indigo for main directory
        }
        return '#4f46e5';  // Indigo for included files
      }

      // Referenced projects section
      if (path[1] === 'referenced') {
        if (path.length === 2) {
          return '#fcd34d';  // Light amber for referenced directory
        }
        if (path.length === 3) {
          return '#f59e0b';  // Amber for project folders
        }
        return '#10b981';  // Emerald for included files
      }

      return '#94a3b8';  // Default gray
    });

    // Create custom hover text
    const customData = plotlyData.ids.map((id, index) => {
      const path = id.split('/');
      const isFile = !this.nodeMap.get(id)?.children?.length;
      let projectType = 'Root';

      if (path[1] === 'main') {
        projectType = 'Main Project';
      } else if (path[1] === 'referenced') {
        projectType = path.length === 3 ? 'Referenced Project' : 'Referenced File';
      }

      return {
        path: id,
        fileCount: isFile ? 1 : this.countFiles(this.nodeMap.get(id)!),
        sizeFormatted: this.formatSizeForHover(plotlyData.values[index]),
        included: plotlyData.included[index] ? 'Included' : 'Excluded',
        isFile,
        projectType
      };
    });

    const plotlyConfig = [{
      type: 'treemap',
      branchvalues: "total",
      labels: plotlyData.labels,
      parents: plotlyData.parents,
      values: plotlyData.values,
      ids: plotlyData.ids,
      textinfo: 'label',
      customdata: customData,
      hovertemplate: `
<b>%{label}</b><br>
%{customdata.projectType}<br>
Size: %{customdata.sizeFormatted}<br>
Files: %{customdata.fileCount}<br>
Status: %{customdata.included}<br>
<extra></extra>`,
      marker: {
        colors: colors,
        showscale: false,
        pad: 2,
        line: {
          width: 0.5,
          color: '#e2e8f0'  // Light border color
        }
      },
      pathbar: {
        visible: true,
        side: 'top',
        thickness: 20
      }
    }];

    const layout = {
      width: chartContainer.offsetWidth,
      height: 800,
      margin: {l: 0, r: 0, t: 30, b: 0},
      padding: {l: 5, r: 5, t: 5, b: 5}
    };

    const config = {
      displayModeBar: false,
      responsive: true
    };

    Plotly.newPlot('file-treemap', plotlyConfig, layout, config);

    // Handle click events
    // @ts-ignore
    chartContainer.on('plotly_click', (d: any) => {
      if (d.points && d.points.length > 0) {
        const point = d.points[0];
        const customData = point.customdata;

        this.selectedNode = {
          path: point.id,
          size: point.value,
          totalSize: point.value
        };

        // If clicked node is a file, show preview
        if (customData.isFile) {
          const fileInfo = this.fileNodeMap.get(point.id);
          if (fileInfo) {
            this.viewFileContent(fileInfo);
          }
        }
      }
    });
  }

  private flattenTree(node: any, parentId: string = ''): TreemapData {
    const data: TreemapData = {
      labels: [],
      parents: [],
      values: [],
      ids: [],
      included: []
    };

    const processNode = (node: any, parentId: string) => {
      const currentId = parentId ? `${parentId}/${node.name}` : node.name;

      console.log(`[Treemap] Processing node: ${currentId}`, {
        name: node.name,
        included: node.included,
        size: node.size,
        hasChildren: !!node.children
      });

      data.labels.push(node.name);
      data.parents.push(parentId);
      data.ids.push(currentId);

      // Store node in map for later reference
      this.nodeMap.set(currentId, node);

      if (node.children?.length > 0) {
        // Directory node
        const totalSize = node.children.reduce((sum: number, child: any) => {
          return sum + (child.size || this.calculateNodeSize(child));
        }, 0);
        data.values.push(totalSize);

        // Directory inclusion status is based on children
        const hasIncludedChildren = node.children.some((child: any) => child.included);
        data.included.push(hasIncludedChildren);
        console.log(`[Treemap] Directory ${currentId} inclusion status:`, {
          hasIncludedChildren,
          totalSize
        });

        node.children.forEach((child: any) => processNode(child, currentId));
      } else {
        // File node
        data.values.push(node.size || 0);
        data.included.push(node.included || false);
        console.log(`[Treemap] File ${currentId} inclusion status:`, {
          included: node.included,
          size: node.size
        });
      }
    };

    processNode(node, '');
    return data;
  }

  private calculateNodeSize(node: any): number {
    if (!node.children) {
      return node.size || 0;
    }
    return node.children.reduce((sum: number, child: any) =>
      sum + (child.size || this.calculateNodeSize(child)), 0
    );
  }

  private hasIncludedFiles(node: any): boolean {
    if (!node.children) {
      return node.included || false;
    }
    return node.children.some((child: any) =>
      child.included || (child.children && this.hasIncludedFiles(child))
    );
  }

  viewFileContent(fileInfo: FileInfo) {
    this.isLoadingContent = true;
    this.selectedFile = fileInfo;
    this.fileContent = null;
    this.fileContentError = null;

    // Remove 'root/' prefix and adjust the path
    let fullPath = fileInfo.fullPath;
    if (fullPath.startsWith('root/')) {
      fullPath = fullPath.substring(5); // Remove 'root/'
    }

    console.log('[File Request] Processing path:', {
      originalPath: fileInfo.fullPath,
      adjustedPath: fullPath
    });

    this.fileDataService.getFileContent(fullPath)
      .subscribe({
        next: (response: FileContentResponse) => {
          if (response.error) {
            console.error('[File Request] Server error:', response.error);
            this.fileContentError = response.error;
          } else {
            console.log('[File Request] Successfully loaded file content');
            this.fileContent = response.content;
          }
          this.isLoadingContent = false;
        },
        error: (error) => {
          console.error('[File Request] Failed to load file:', error);
          this.fileContentError = 'Failed to load file content';
          this.isLoadingContent = false;
        }
      });
  }

  clearSelection() {
    this.selectedNode = null;
  }

  formatSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  closeFileContent() {
    this.selectedFile = null;
    this.fileContent = null;
    this.fileContentError = null;
  }

  onShowOnlyIncludedChange() {
    this.updateTreemap();
  }

  getIncludedFilesCount(): number {
    return this.files.filter(f => f.included).length;
  }

  get filteredFiles(): FileInfo[] {
    let filtered = this.files;

    if (this.showOnlyIncluded) {
      filtered = filtered.filter(f => f.included);
    }

    if (this.filterText.trim()) {
      const searchText = this.filterText.toLowerCase();
      filtered = filtered.filter(f =>
        f.name.toLowerCase().includes(searchText) ||
        f.path.toLowerCase().includes(searchText) ||
        `${f.path}/${f.name}`.toLowerCase().includes(searchText)
      );
    }

    return filtered;
  }

  clearFilter() {
    this.filterText = '';
  }

  public reload() {
    this.loadTreemapData();
  }
}

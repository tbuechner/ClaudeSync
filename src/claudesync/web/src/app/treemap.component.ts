import {Component, OnInit, OnDestroy, Input} from '@angular/core';
import { CommonModule } from '@angular/common';
import {FileContentResponse, FileDataService, SyncData} from './file-data.service';
import { HttpClient } from '@angular/common/http';
import {finalize} from 'rxjs/operators';
import { takeUntil } from 'rxjs/operators';
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

  files: FileInfo[] = [];
  private fileNodeMap = new Map<string, FileInfo>();

  filterText = '';

  private currentSubscription?: Subscription;

  @Input() set syncData(data: SyncData | null) {
    if (data) {
      this.originalTreeData = data.treemap;
      this.updateTreemap();
      const plotlyData = this.flattenTree(data.treemap);
      this.renderTreemap(plotlyData);
      this.updateFilesList(data.treemap);
    }
  }

  constructor(private http: HttpClient, private fileDataService: FileDataService) {}

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
      const plotlyData = this.flattenTree(filteredData);
      this.renderTreemap(plotlyData);
      this.updateFilesList(this.originalTreeData);
    }
  }

  private flattenTree(rootNode: any): TreemapData {
    const data: TreemapData = {
      labels: ['root', 'main', 'referenced'],
      parents: ['', 'root', 'root'],
      values: [0, 0, 0],
      ids: ['root', 'main', 'referenced'],
      included: [true, true, true]
    };
    (data as any).customdata = [
      { fileCount: 0, source: '', isRoot: true, isSection: false, sizeFormatted: '0 B' },
      { fileCount: 0, source: 'main', isRoot: false, isSection: true, sizeFormatted: '0 B' },
      { fileCount: 0, source: 'referenced', isRoot: false, isSection: true, sizeFormatted: '0 B' }
    ];

    // Calculate total size for a node and all its children
    const calculateNodeSize = (node: any): number => {
      if (!node) return 0;
      let totalSize = node.size || 0;

      if (node.children) {
        node.children.forEach((child: any) => {
          totalSize += calculateNodeSize(child);
        });
      }

      return totalSize;
    };

    const processNode = (node: any, parentId: string, source: string): number => {
      if (!node) return 0;
      if (node.name === 'root' || node.name === 'main' || node.name === 'referenced') return 0;

      const currentId = parentId ? `${parentId}/${node.name}` : node.name;

      // Calculate the total size of this node and all its children
      const totalSize = calculateNodeSize(node);
      console.log(`Calculated total size for ${node.name}:`, totalSize);

      // Create complete customdata object
      const customDataObject = {
        fileCount: node.children ? node.children.length : 0,
        sizeFormatted: this.formatSizeForHover(totalSize),
        included: node.included !== false,
        isFile: !node.children || node.children.length === 0,
        source: source
      };

      // Add all data at once
      data.labels.push(node.name);
      data.parents.push(parentId);
      data.ids.push(currentId);
      data.values.push(totalSize);
      data.included.push(node.included !== false);
      (data as any).customdata.push(customDataObject);

      // Process children
      if (node.children && node.children.length > 0) {
        console.log(`Processing ${node.children.length} children for ${node.name}`);
        // @ts-ignore
        node.children.forEach(child => {
          processNode(child, currentId, source);
        });
      }

      return totalSize;
    };

    // Process main section
    const mainNode = rootNode.children?.find((c: any) => c.name === 'main');
    if (mainNode?.children) {
      // @ts-ignore
      const mainTotal = mainNode.children.reduce((sum, child) => {
        return sum + processNode(child, 'main', 'main');
      }, 0);
      data.values[1] = mainTotal;
      (data as any).customdata[1].sizeFormatted = this.formatSizeForHover(mainTotal);
    }

    // Process referenced section
    const referencedNode = rootNode.children?.find((c: any) => c.name === 'referenced');
    if (referencedNode?.children) {
      let referencedTotal = 0;

      referencedNode.children.forEach((projectNode: any) => {
        const projectId = projectNode.name;
        const projectNodeId = `referenced/${projectId}`;

        // Calculate total project size first
        const projectTotal = calculateNodeSize(projectNode);
        console.log(`Project ${projectId} calculated total size:`, projectTotal);

        // Add project node
        data.labels.push(projectId);
        data.parents.push('referenced');
        data.ids.push(projectNodeId);
        data.values.push(projectTotal);
        data.included.push(projectNode.included !== false);
        (data as any).customdata.push({
          fileCount: projectNode.children?.length || 0,
          source: 'referenced',
          isRoot: false,
          isSection: true,
          sizeFormatted: this.formatSizeForHover(projectTotal)
        });

        // Process project's files
        if (projectNode.children) {
          // @ts-ignore
          projectNode.children.forEach(child => {
            processNode(child, projectNodeId, `referenced/${projectId}`);
          });
        }

        referencedTotal += projectTotal;
      });

      // Update referenced section total
      data.values[2] = referencedTotal;
      (data as any).customdata[2].sizeFormatted = this.formatSizeForHover(referencedTotal);
    }

    // Update root value as sum of all sections
    data.values[0] = data.values[1] + data.values[2];
    (data as any).customdata[0].sizeFormatted = this.formatSizeForHover(data.values[0]);

    return data;
  }

  private updateFilesList(treeData: any) {
    const files: FileInfo[] = [];
    this.fileNodeMap.clear();

    const processNode = (node: any, parentPath: string = '', source: string = '') => {
      const currentPath = parentPath ? `${parentPath}/${node.name}` : node.name;

      if ('size' in node) {
        const pathParts = currentPath.split('/');
        pathParts.shift(); // Remove the first element (root directory name)
        const fileName = pathParts.pop() || '';
        const filePath = pathParts.join('/');

        const fileInfo: FileInfo = {
          name: fileName,
          path: filePath,
          fullPath: currentPath,
          size: node.size,
          included: node.included,
          source
        };

        files.push(fileInfo);
        this.fileNodeMap.set(currentPath, fileInfo);
      } else if (node.children) {
        node.children.forEach((child: any) => processNode(child, currentPath, source));
      }
    };

    // Process main and referenced sections separately
    if (treeData.children) {
      const mainNode = treeData.children.find((c: any) => c.name === 'main');
      const referencedNode = treeData.children.find((c: any) => c.name === 'referenced');

      if (mainNode) {
        processNode(mainNode, '', 'main');
      }
      if (referencedNode) {
        processNode(referencedNode, '', 'referenced');
      }
    }

    this.files = files.sort((a, b) => a.fullPath.localeCompare(b.fullPath));
  }

  private buildTree(data: TreemapData): Map<string, TreeNode> {
    const nodeMap = new Map<string, TreeNode>();

    // First pass: create all nodes
    for (let i = 0; i < data.ids.length; i++) {
      nodeMap.set(data.ids[i], {
        id: data.ids[i],
        label: data.labels[i],
        value: data.values[i],
        children: [],
      });
    }

    // Second pass: build relationships
    for (let i = 0; i < data.ids.length; i++) {
      const parentId = data.parents[i];
      if (parentId && nodeMap.has(parentId)) {
        const parent = nodeMap.get(parentId)!;
        parent.children.push(nodeMap.get(data.ids[i])!);
      }
    }

    return nodeMap;
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

  private getNodeInclusionStatus(node: any): 'included' | 'excluded' | 'partial' {
    if (!node.children) {
      // For leaf nodes (files), directly use the included property
      return node.included ? 'included' : 'excluded';
    }

    // For directories, check children recursively
    let hasIncluded = false;
    let hasExcluded = false;

    const checkChildren = (childNode: any) => {
      if (!childNode.children) {
        // Leaf node
        if (childNode.included) {
          hasIncluded = true;
        } else {
          hasExcluded = true;
        }
      } else {
        // Directory node - process all children
        childNode.children.forEach(checkChildren);
      }
    };

    // Process all children
    node.children.forEach(checkChildren);

    // Determine status based on children
    if (hasIncluded && hasExcluded) {
      return 'partial';
    } else if (hasIncluded) {
      return 'included';
    } else {
      return 'excluded';
    }
  }

  private findNodeInTree(tree: any, nodeName: string): any {
    if (tree.name === nodeName) {
      return tree;
    }

    if (tree.children) {
      for (const child of tree.children) {
        const found = this.findNodeInTree(child, nodeName);
        if (found) return found;
      }
    }

    return null;
  }

  clearFilter() {
    this.filterText = '';
  }

  private countFiles(node: TreeNode): number {
    if (node.children.length === 0) {
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

  public loadTreemapData() {
    // Unsubscribe from any existing subscription
    this.currentSubscription?.unsubscribe();

    this.isLoading = true;
    console.log('Loading treemap data');

    // Store the new subscription
    this.currentSubscription = this.fileDataService.getSyncData()
      .subscribe({
        next: (data) => {
          this.originalTreeData = data.treemap;
          this.updateTreemap();
          const plotlyData = this.flattenTree(data.treemap);
          this.renderTreemap(plotlyData);
          this.updateFilesList(data.treemap);
          this.isLoading = false;
          console.log('Finished loading treemap data');
        },
        error: (error) => {
          console.error('Error loading treemap data:', error);
          this.isLoading = false;
        }
      });
  }

  public reload() {
    this.loadTreemapData();
  }

  private getNodeColor(included: boolean, source: string, isRoot: boolean = false): string {
    if (isRoot) return '#f8fafc'; // Very light gray for root
    if (!included) return '#94a3b8'; // Gray for excluded files

    // Handle section headers (main/referenced)
    if (source === 'main' && !included) return '#818cf8'; // Lighter indigo for main section
    if (source === 'referenced' && !included) return '#86efac'; // Lighter green for referenced section

    // Handle actual files
    return source === 'main' ? '#4f46e5' : '#22c55e'; // Indigo for main, green for referenced files
  }

  private renderTreemap(data: TreemapData) {
    const chartContainer = document.getElementById('file-treemap');
    if (!chartContainer) {
      console.warn('Chart container not found');
      return;
    }

    // Build tree structure and calculate file counts
    const nodeMap = this.buildTree(data);
    const colors = data.labels.map((label: string, index: number) => {
      const customData = (data as any).customdata[index];
      const isRoot = label === 'root';
      const isMainOrReferenced = label === 'main' || label === 'referenced';
      return this.getNodeColor(data.included[index], customData.source, isRoot || isMainOrReferenced);
    });

    const plotlyData = [{
      type: 'treemap',
      branchvalues: "total",
      labels: data.labels,
      parents: data.parents,
      values: data.values,
      ids: data.ids,
      textinfo: 'label',
      customdata: (data as any).customdata,
      hovertemplate: `
<b>%{label}</b><br>
Size: %{customdata.sizeFormatted}<br>
Files: %{customdata.fileCount}<br>
Source: %{customdata.source}<br>
Status: %{customdata.included ? 'Included' : 'Excluded'}<br>
<extra></extra>`,
      marker: {
        colors: colors,
        showscale: false
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
      margin: { l: 0, r: 0, t: 30, b: 0 },
    };

    const config = {
      displayModeBar: false,
      responsive: true
    };

    // Create the plot and attach the click handler
    Plotly.newPlot('file-treemap', plotlyData, layout, config);

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

        console.log('Selected node:', this.selectedNode);

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

  clearSelection() {
    this.selectedNode = null;
  }

  copySelection() {
    if (this.selectedNode) {
      // Remove the "root/" prefix if it exists
      const path = this.selectedNode.path.replace(/^root\//, '');
      navigator.clipboard.writeText(path).then(() => {
        // Optional: You could add a temporary visual feedback here
        console.log('Path copied to clipboard:', path);
      }).catch(err => {
        console.error('Failed to copy text: ', err);
      });
    }
  }

  getSelection(): string {
    if (this.selectedNode) {
      // Remove the "root/" prefix if it exists
      return this.selectedNode.path.replace(/^root\//, '');
    }
    return '';
  }

  formatSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  viewFileContent(file: FileInfo) {
    this.isLoadingContent = true;
    this.selectedFile = file;
    this.fileContent = null;
    this.fileContentError = null;

    const fullPath = file.path ? `${file.path}/${file.name}` : file.name;

    this.fileDataService.getFileContent(fullPath)
      .subscribe({
        next: (response: FileContentResponse) => {
          if (response.error) {
            this.fileContentError = response.error;
          } else {
            this.fileContent = response.content;
          }
          this.isLoadingContent = false;
        },
        error: (error) => {
          console.error('Error loading file content:', error);
          this.fileContentError = 'Failed to load file content';
          this.isLoadingContent = false;
        }
      });
  }

  closeFileContent() {
    this.selectedFile = null;
    this.fileContent = null;
    this.fileContentError = null;
  }

  onShowOnlyIncludedChange() {
    this.updateTreemap();
  }
}

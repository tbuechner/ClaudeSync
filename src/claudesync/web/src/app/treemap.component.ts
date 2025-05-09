import {Component, OnInit, OnDestroy, Input, EventEmitter, Output, ChangeDetectorRef} from '@angular/core';
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
import { NodeActionsMenuComponent } from './node-actions-menu.component';
import { DropZoneComponent, DroppedFile } from './drop-zone.component';
import { NotificationService } from './notification.service';

declare const Plotly: any;

@Component({
  selector: 'app-treemap',
  standalone: true,
  imports: [CommonModule, FormsModule, FilePreviewComponent, ModalComponent, DropZoneComponent],
  templateUrl: './treemap.component.html',
  styleUrls: ['./treemap.component.css']
})
export class TreemapComponent implements OnDestroy {
  hiddenFolders: Set<string> = new Set<string>();
  hasHiddenFolders: boolean = false;

  @Input() set syncData(data: SyncData | null) {
    if (data) {
      console.debug('TreemapComponent received new syncData');

      // Check if there was a timeout in file traversal
      this.timeoutOccurred = data.timeout || false;
      this.timeoutMessage = data.timeoutMessage || 'File traversal timed out.';

      if (!this.timeoutOccurred) {
        this.originalTreeData = data.treemap;
        this.updateTreemap();
      } else {
        // Clear treemap data to avoid displaying stale information
        this.clearTreemap();
        // Display message in the treemap area
        const chartContainer = document.getElementById('file-treemap');
        this.renderTimeoutMessage(chartContainer);
      }
    } else {
      // Handle null data - clear the treemap
      this.clearTreemap();
    }
  }

  private clearTreemap(): void {
    this.originalTreeData = null;
    this.files = [];
    this.selectedNode = null;

    // Clear the treemap visualization
    const chartContainer = document.getElementById('file-treemap');
    if (chartContainer) {
      Plotly.purge(chartContainer);
      // Add a loading indicator
      chartContainer.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100%;color:#6b7280;font-size:1.125rem;">Loading project data...</div>';
    }
  }

  selectedNode: SelectedNode | null = null;
  showFileList = false;
  private destroy$ = new Subject<void>();
  private baseUrl = 'http://localhost:4201/api';

  selectedFile: FileInfo | null = null;
  fileContent: string | null = null;
  fileContentError: string | null = null;

  private originalTreeData: any = null;

  files: FileInfo[] = [];
  private fileNodeMap = new Map<string, FileInfo>();

  filterText = '';

  // New properties for timeout handling
  timeoutOccurred = false;
  timeoutMessage = '';

  private currentSubscription?: Subscription;

  constructor(
    private http: HttpClient,
    private fileDataService: FileDataService,
    private notificationService: NotificationService,
    private changeDetectorRef: ChangeDetectorRef
  ) {}

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

  public updateTreemap() {
    if (!this.originalTreeData) return;

    const plotlyData = this.flattenTree(this.originalTreeData);
    this.renderTreemap(plotlyData);
    this.updateFilesList(this.originalTreeData);
  }

  // New method to render timeout message
  private renderTimeoutMessage(container: HTMLElement | null) {
    if (!container) return;

    // Create message element
    const messageDiv = document.createElement('div');
    messageDiv.className = 'timeout-message';
    messageDiv.style.width = '100%';
    messageDiv.style.height = '100%';
    messageDiv.style.display = 'flex';
    messageDiv.style.flexDirection = 'column';
    messageDiv.style.alignItems = 'center';
    messageDiv.style.justifyContent = 'center';
    messageDiv.style.textAlign = 'center';
    messageDiv.style.padding = '2rem';

    // Create icon element
    const iconDiv = document.createElement('div');
    iconDiv.innerHTML = `
      <svg viewBox="0 0 24 24" width="48" height="48" style="margin-bottom: 1rem; color: #f59e0b;">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"
              fill="currentColor" />
      </svg>
    `;

    // Create heading
    const heading = document.createElement('h3');
    heading.style.fontSize = '1.25rem';
    heading.style.fontWeight = '600';
    heading.style.marginBottom = '0.75rem';
    heading.style.color = '#1e293b';
    heading.textContent = 'File Traversal Timeout';

    // Create message text
    const message = document.createElement('p');
    message.style.fontSize = '1rem';
    message.style.color = '#64748b';
    message.style.maxWidth = '600px';
    message.textContent = this.timeoutMessage;

    // Create suggestions
    const suggestions = document.createElement('div');
    suggestions.style.marginTop = '1.5rem';
    suggestions.style.fontSize = '0.875rem';
    suggestions.style.color = '#64748b';
    suggestions.innerHTML = `
      <p><strong>Suggestions:</strong></p>
      <ul style="text-align: left; margin-top: 0.5rem;">
        <li>Use more specific include patterns in your project configuration</li>
        <li>Add more exclude patterns or update your .claudeignore file</li>
      </ul>
    `;

    // Assemble the message
    messageDiv.appendChild(iconDiv);
    messageDiv.appendChild(heading);
    messageDiv.appendChild(message);
    messageDiv.appendChild(suggestions);

    // Clear and add to container
    container.innerHTML = '';
    container.appendChild(messageDiv);
  }

  private flattenTree(node: any, parentId: string = ''): TreemapData {
    const data: TreemapData = {
      labels: [],
      parents: [],
      values: [],
      ids: [],
      included: []
    };

    // Calculate directory sizes first
    const calculateSize = (node: any): number => {
      if ('size' in node) {
        return node.size;
      }
      return (node.children || []).reduce((sum: number, child: any) => sum + calculateSize(child), 0);
    };

    const processNode = (node: any, parentId: string) => {
      const currentId = parentId ? `${parentId}/${node.name}` : node.name;

      // Skip this node and its children if it's in the hiddenFolders set
      // (but only if it's not the root node)
      if (currentId !== 'root' && this.hiddenFolders.has(this.getPathWithoutRoot(currentId))) {
        return;
      }

      data.labels.push(node.name);
      data.parents.push(parentId);
      data.ids.push(currentId);

      // For both files and directories, calculate the total size
      const totalSize = calculateSize(node);
      data.values.push(totalSize);

      // For files, use the included property directly
      // For directories, check if any children are included
      const isIncluded = 'included' in node ? node.included :
        (node.children || []).some((child: any) =>
          'included' in child ? child.included : false
        );
      data.included.push(isIncluded);

      // Process children if they exist
      if (node.children) {
        node.children.forEach((child: any) => {
          processNode(child, currentId);
        });
      }
    };

    processNode(node, '');
    return data;
  }

  private updateFilesList(treeData: any) {
    const files: FileInfo[] = [];
    this.fileNodeMap.clear();

    const processNode = (node: any, parentPath: string = '') => {
      const currentPath = parentPath ? `${parentPath}/${node.name}` : node.name;

      if ('size' in node) {
        // This is a file node
        const pathParts = currentPath.split('/');
        pathParts.shift(); // Remove the first element (root directory name)
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
        // This is a directory node - process its children
        node.children.forEach((child: any) => processNode(child, currentPath));
      }
    };

    processNode(treeData);
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
        children: []
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

  private renderTreemap(data: TreemapData) {
    this.updateFilesList(data);
    const chartContainer = document.getElementById('file-treemap');
    if (!chartContainer) {
      console.warn('Chart container not found');
      return;
    }

    // Don't attempt to render if timeout occurred
    if (this.timeoutOccurred) {
      this.renderTimeoutMessage(chartContainer);
      return;
    }

    // Build tree structure and calculate file counts
    const nodeMap = this.buildTree(data);
    const fileCountMap = new Map<string, number>();
    const inclusionStatusMap = new Map<string, string>();  // Added this line

    // Calculate file counts for each node
    for (const [id, node] of nodeMap) {
      fileCountMap.set(id, this.countFiles(node));
    }

    // Process nodes to calculate file counts and inclusion status
    const processNode = (id: string) => {
      const node = nodeMap.get(id);
      if (!node) return;

      // Calculate file count
      fileCountMap.set(id, this.countFiles(node));

      // Calculate inclusion status by checking the original tree data
      let treeNode = this.findNodeInTree(this.originalTreeData, node.label);
      if (treeNode) {
        inclusionStatusMap.set(id, this.getNodeInclusionStatus(treeNode));
      }

      // Process children
      node.children.forEach(child => processNode(child.id));
    };

    // Start processing from root nodes (nodes with no parents)
    data.ids.forEach((id, index) => {
      if (!data.parents[index]) {
        processNode(id);
      }
    });
    // Create custom text array for hover info
    const customData = data.ids.map((id, index) => ({
      fileCount: fileCountMap.get(id) || 0,
      sizeFormatted: this.formatSizeForHover(nodeMap.get(id)?.value || 0),
      included: inclusionStatusMap.get(id),
      isFile: !nodeMap.get(id)?.children?.length
    }));

    // Create color array based on included status
    const colors = data.ids.map(id => {
      const status = inclusionStatusMap.get(id);
      switch (status) {
        case 'included':
          return '#4f46e5'; // Indigo for included
        case 'partial':
          return '#eab308'; // Yellow for partially included
        default:
          return '#94a3b8'; // Gray for excluded
      }
    });

    const plotlyData = [{
      type: 'treemap',
      branchvalues: "total",
      labels: data.labels,
      parents: data.parents,
      values: data.values,
      ids: data.ids,
      textinfo: 'label',
      customdata: customData,
      hovertemplate: `
<b>%{label}</b><br>
Size: %{customdata.sizeFormatted}<br>
Files: %{customdata.fileCount}<br>
Status: %{customdata.included}<br>
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

  private getPathWithoutRoot(path: string): string {
    // Remove the "root/" prefix if it exists
    return path.replace(/^root\//, '');
  }

  /**
   * Determines if the selected node is a folder based on its path
   */
  isSelectedNodeFolder(): boolean {
    if (!this.selectedNode) return false;

    // Simple check - if the node doesn't have a file extension, it's likely a folder
    // Could improve this by checking if it has children in the tree structure
    const nodePath = this.selectedNode.path;
    const lastSegment = nodePath.split('/').pop() || '';

    // No file extension and not empty
    return lastSegment.indexOf('.') === -1 && lastSegment.length > 0;
  }

  /**
   * Load all files in the selected folder, including those not included in the sync
   */
  hideSelectedFolder(): void {
    if (!this.selectedNode || !this.isSelectedNodeFolder()) {
      return;
    }

    const folderPath = this.getSelection();
    this.hiddenFolders.add(folderPath);
    this.hasHiddenFolders = true;

    // Update the visualization
    this.updateTreemap();

    // Clear selection after hiding
    this.clearSelection();

    this.notificationService.info(`Folder "${folderPath}" hidden from view`);
  }

  resetView(): void {
    if (this.hiddenFolders.size === 0) {
      return;
    }

    this.hiddenFolders.clear();
    this.hasHiddenFolders = false;
    this.updateTreemap();

    this.notificationService.info('View reset, all folders are now visible');
  }

  loadAllFolderContents(): void {
    console.log('loadAllFolderContents called');

    if (!this.selectedNode) {
      console.warn('No node selected');
      this.notificationService.warning('No folder selected');
      return;
    }

    if (!this.isSelectedNodeFolder()) {
      console.warn(`Selected node is not a folder: ${this.selectedNode.path}`);
      this.notificationService.warning('Selected node is not a folder');
      return;
    }

    // Get the folder path without the root prefix
    const folderPath = this.getSelection();
    console.log(`Loading all files for folder: "${folderPath}"`);

    this.notificationService.info(`Loading all files in ${folderPath}...`);

    this.fileDataService.getFolderContents(folderPath)
      .subscribe({
        next: (response) => {
          console.log('Folder contents API response:', response);

          if (!response.success) {
            console.error('API reported failure');
            this.notificationService.error('Failed to load folder contents');
            return;
          }

          if (!response.contents) {
            console.error('API response missing contents data');
            this.notificationService.error('Invalid response format');
            return;
          }

          console.log(`Received folder contents with ${response.contents.children?.length || 0} items`);

          // Update the folder contents in the treemap
          this.updateFolderContentsInTreemap(folderPath, response.contents);

          // Refresh the visualization
          console.log('Updating treemap visualization');
          this.updateTreemap();

          this.notificationService.success('Folder contents loaded');
        },
        error: (error) => {
          console.error('Error loading folder contents:', error);
          this.notificationService.error('Failed to load folder contents: ' + (error.message || 'Unknown error'));
        }
      });
  }

  /**
   * Update a specific folder's contents in the treemap data structure
   */
  private updateFolderContentsInTreemap(folderPath: string, newContents: any): void {
    console.log('updateFolderContentsInTreemap - folderPath:', folderPath);
    console.log('updateFolderContentsInTreemap - newContents structure:', newContents ? (newContents.children ? `Has ${newContents.children.length} children` : 'No children array') : 'null');

    if (!this.originalTreeData) {
      console.error('originalTreeData is null or undefined, cannot update treemap');
      return;
    }

    // Clone the original data to avoid reference issues
    const updatedData = JSON.parse(JSON.stringify(this.originalTreeData));
    console.log('updateFolderContentsInTreemap - cloned originalTreeData structure:',
      `Name: ${updatedData.name}, Children: ${updatedData.children ? updatedData.children.length : 0}`);

    // Log the first level of children to understand the structure
    if (updatedData.children && updatedData.children.length > 0) {
      console.log('First level children names:');
      updatedData.children.forEach((child: any, index: number) => {
        console.log(`  Child ${index}: ${child.name}`);
        if (child.children && child.children.length > 0) {
          console.log(`    Subchildren of ${child.name}:`);
          child.children.forEach((subchild: any, subindex: number) => {
            console.log(`      Subchild ${subindex}: ${subchild.name}`);
          });
        }
      });
    }

    // Find the target folder and replace its children
    const pathParts = folderPath.split('/');
    console.log('updateFolderContentsInTreemap - pathParts:', pathParts);

    // Handle root folder case
    if (folderPath === '' || folderPath === '.') {
      console.log('updateFolderContentsInTreemap - handling root folder case');
      if (newContents && newContents.children) {
        console.log(`Replacing root's ${updatedData.children?.length || 0} children with ${newContents.children.length} new children`);
        updatedData.children = newContents.children;
        this.originalTreeData = updatedData;
        console.log('updateFolderContentsInTreemap - updated root folder children');
      } else {
        console.error('newContents is missing children array');
      }
      return;
    }

    // MODIFIED: Find node by path using a different approach
    // Instead of expecting the tree to match exactly the path parts,
    // search for matching nodes at each level of the tree
    const findNodeByPath = (node: any, path: string): any => {
      console.log(`Finding node for path: ${path}`);

      // Handle root case
      if (path === '' || path === '.') {
        console.log('Returning root node');
        return node;
      }

      // This is a direct match
      if (node.name === path) {
        console.log(`Found exact match for ${path}`);
        return node;
      }

      // Check if any children have the full path or match the pattern
      if (node.children) {
        // First try to find the exact path in any child
        for (const child of node.children) {
          if (child.name === path) {
            console.log(`Found exact match for ${path} in children`);
            return child;
          }

          // Check if the node name ends with the last part of the path
          const pathParts = path.split('/');
          const lastPart = pathParts[pathParts.length - 1];
          if (child.name === lastPart) {
            console.log(`Found match for last part ${lastPart} in children`);
            return child;
          }
        }

        // Then check recursively in all children
        for (const child of node.children) {
          if (child.children && child.children.length > 0) {
            // Recursively check this child's children
            const foundNode = findNodeByPath(child, path);
            if (foundNode) {
              console.log(`Found node for ${path} in subtree of ${child.name}`);
              return foundNode;
            }
          }
        }
      }

      // If we didn't find a matching node, check if we should go down a level
      // based on the first part of the path
      const pathParts = path.split('/');
      if (pathParts.length > 1) {
        const firstPart = pathParts[0];
        const remainingPath = pathParts.slice(1).join('/');

        // Try to find a child that matches the first part
        if (node.children) {
          for (const child of node.children) {
            if (child.name === firstPart && child.children) {
              console.log(`Descending into ${firstPart} to find ${remainingPath}`);
              const foundNode = findNodeByPath(child, remainingPath);
              if (foundNode) {
                return foundNode;
              }
            }
          }
        }
      }

      // Last attempt: If this is a path with no slashes, search all children deeply
      if (!path.includes('/') && node.children) {
        for (const child of node.children) {
          if (child.children && child.children.length > 0) {
            const foundNode = findDeepNodeByName(child, path);
            if (foundNode) {
              console.log(`Found node with deep search for ${path}`);
              return foundNode;
            }
          }
        }
      }

      return null;
    };

    // Helper function to search deeply for a node by name
    const findDeepNodeByName = (node: any, name: string): any => {
      if (node.name === name) {
        return node;
      }

      if (node.children) {
        for (const child of node.children) {
          const found = findDeepNodeByName(child, name);
          if (found) {
            return found;
          }
        }
      }

      return null;
    };

    // Try to find the target node
    const targetNode = findNodeByPath(updatedData, folderPath);

    if (targetNode) {
      console.log(`Found target node: ${targetNode.name} with ${targetNode.children ? targetNode.children.length : 0} existing children`);
      if (newContents && newContents.children) {
        // Replace the node's children
        targetNode.children = newContents.children;
        console.log(`Updated children array with ${newContents.children.length} items`);
      } else {
        console.error('newContents is missing children array');
      }
    } else {
      console.error(`Failed to find folder node at path: ${folderPath}`);
      // Log the first level of the tree structure to help debug
      if (updatedData.children) {
        console.log('First level children in tree:');
        updatedData.children.forEach((child: any, index: number) => {
          console.log(`  ${index}: ${child.name}`);
        });
      }
    }

    // Replace the original data with the updated version regardless of whether we found the node
    this.originalTreeData = updatedData;
    console.log('updateFolderContentsInTreemap - completed, originalTreeData updated');
  }

  formatSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  viewFileContent(file: FileInfo) {
    // Don't allow file viewing in timeout state
    if (this.timeoutOccurred) {
      this.notificationService.warning('File content cannot be viewed in timeout state');
      return;
    }

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
        },
        error: (error) => {
          console.error('Error loading file content:', error);
          this.fileContentError = 'Failed to load file content';
        }
      });
  }

  closeFileContent() {
    this.selectedFile = null;
    this.fileContent = null;
    this.fileContentError = null;
  }

  handleNodeAction(action: string) {
    if (!this.selectedNode) return;

    // Disable actions in timeout state
    if (this.timeoutOccurred && action !== 'copy') {
      this.notificationService.warning('Cannot perform this action in timeout state');
      return;
    }

    // Remove the "root/" prefix if it exists
    const path = this.selectedNode.path.replace(/^root\//, '');

    switch (action) {
      case 'copy':
        this.copySelection();
        break;

      case 'addToIncludes':
        this.updateConfigIncrementally({
          action: 'addInclude',
          pattern: path
        });
        break;

      case 'removeFromIncludes':
        this.updateConfigIncrementally({
          action: 'removeInclude',
          pattern: path
        });
        break;

      case 'addToExcludes':
        this.updateConfigIncrementally({
          action: 'addExclude',
          pattern: path
        });
        break;

      case 'removeFromExcludes':
        this.updateConfigIncrementally({
          action: 'removeExclude',
          pattern: path
        });
        break;

      case 'hideFolder':
        this.hideSelectedFolder();
        break;

      case 'clear':
        this.clearSelection();
        break;
    }
  }

  private updateConfigIncrementally(config: { action: string, pattern: string }) {
    this.fileDataService.updateConfigIncrementally(config)
      .subscribe({
        next: (response) => {
        },
        error: (error) => {
          console.error('Error updating configuration:', error);
        }
      });
  }

  onFilesDropped(files: DroppedFile[]): void {
    // Disable file drop in timeout state
    if (this.timeoutOccurred) {
      this.notificationService.warning('Cannot process files in timeout state');
      return;
    }

    if (!files.length) return;

    this.notificationService.info(`Processing ${files.length} file(s)...`);

    this.fileDataService.resolveDroppedFiles(files)
      .subscribe({
        next: (response) => {
          if (!response.success) {
            this.notificationService.error('Failed to process files');
            return;
          }

          const results = response.results || [];
          const resolvedFiles = results.filter((r: any) => r.resolved);
          const unresolvedFiles = results.filter((r: any) => !r.resolved);

          // Process successful matches
          if (resolvedFiles.length > 0) {
            // Add resolved paths to includes
            this.processResolvedFiles(resolvedFiles);
            this.notificationService.success(
              `Successfully matched and added ${resolvedFiles.length} file(s)`
            );
          }

          // Notify about unresolved files
          if (unresolvedFiles.length > 0) {
            this.notificationService.warning(
              `Could not match ${unresolvedFiles.length} file(s) to project content`
            );
          }
        },
        error: (error) => {
          console.error('Error processing dropped files:', error);
          this.notificationService.error('Failed to process dropped files');
        }
      });
  }

  private processResolvedFiles(resolvedFiles: any[]): void {
    // Extract all unique paths from resolved files
    const pathsToAdd: string[] = [];

    resolvedFiles.forEach(file => {
      // For each file that was resolved, extract the paths
      (file.paths || []).forEach((path: string) => {
        if (!pathsToAdd.includes(path)) {
          pathsToAdd.push(path);
        }
      });
    });

    // Add each path to the includes list
    pathsToAdd.forEach((path, index) => {
      setTimeout(() => {
        this.updateConfigIncrementally({
          action: 'addInclude',
          pattern: path
        });
      }, index * 200); // Stagger updates to avoid race conditions
    });
  }
}

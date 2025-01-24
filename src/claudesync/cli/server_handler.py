import http.server
import json
import logging
import os
import socketserver
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

import click
from pathspec import pathspec

from ..project_references_manager import ProjectReferencesManager

logger = logging.getLogger(__name__)


class SyncDataHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, config=None, **kwargs):
        self.config = config
        super().__init__(*args, **kwargs)

    def send_cors_headers(self):
        """Send CORS headers for cross-origin requests."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)

        if parsed_path.path == '/api/sync-data':
            self.handle_sync_data()
        elif parsed_path.path == '/api/projects':
            self.handle_projects()
        elif parsed_path.path.startswith('/api/file-content'):
            self.handle_file_content(query_params)
        else:
            super().do_GET()

    def handle_sync_data(self):
        """Handle request for sync data including referenced projects."""
        try:
            active_project = self.get_active_project()
            if not active_project:
                self.send_error_response(400, "No active project found")
                return

            # Get project root and ensure .claudesync directory exists
            project_root = self.config.get_project_root()
            if not project_root:
                self.send_error_response(500, "Project root not found")
                return

            claudesync_dir = Path(project_root) / ".claudesync"
            if not claudesync_dir.exists():
                self.send_error_response(500, "No .claudesync directory found")
                return

            ref_manager = ProjectReferencesManager(claudesync_dir)

            # Get files from main and referenced projects
            files_by_project = ref_manager.get_all_project_files(active_project)

            # Get project configurations
            project_config = ref_manager._get_project_config(active_project)

            # Get referenced projects for root paths
            referenced_projects = ref_manager.get_referenced_projects(active_project)
            logger.debug(f"Referenced projects: {referenced_projects}")

            # Structure project roots
            project_roots = {
                'main': str(self.config.get_project_root()),
                'referenced': {
                    project_id: str(project_path.parent.parent)
                    for project_id, project_path in referenced_projects.items()
                }
            }

            # Generate treemap data with the project configuration
            treemap_data = self.generate_treemap_data(files_by_project, project_roots, ref_manager, active_project)

            # Read .claudeignore file
            claudeignore_path = Path(project_root) / '.claudeignore'
            claudeignore = ''
            if claudeignore_path.exists():
                with open(claudeignore_path, 'r') as f:
                    claudeignore = f.read()

            response_data = {
                'project': project_config,
                'files': files_by_project,
                'projectRoots': project_roots,
                'treemap': treemap_data,
                'claudeignore': claudeignore,
                'stats': self.get_stats(files_by_project)
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            logger.error(f"Error processing sync data request: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.send_error_response(500, str(e))

    def generate_treemap_data(self, files_by_project, project_roots, ref_manager, active_project):
        """Generate treemap data with included/excluded status."""
        root = {
            'name': 'root',
            'children': [
                {
                    'name': 'main',
                    'children': []
                },
                {
                    'name': 'referenced',
                    'children': []
                }
            ]
        }

        def is_file_included(file_path, config):
            """Determine if a file should be included based on include/exclude patterns."""
            includes = config.get("includes", [])
            excludes = config.get("excludes", [])

            logger.debug(f"\nChecking inclusion for file: {file_path}")
            logger.debug(f"Include patterns: {includes}")
            logger.debug(f"Exclude patterns: {excludes}")

            # If no includes specified, nothing is included by default
            if not includes:
                logger.debug(f"No include patterns specified, excluding file")
                return False

            # Create PathSpec objects
            include_spec = pathspec.PathSpec.from_lines("gitwildmatch", includes)
            exclude_spec = None if not excludes else pathspec.PathSpec.from_lines("gitwildmatch", excludes)

            # First check exclusions
            if exclude_spec and exclude_spec.match_file(file_path):
                logger.debug(f"File matches exclude pattern: {file_path}")
                return False

            # Then check inclusions
            is_included = include_spec.match_file(file_path)
            logger.debug(f"File inclusion status: {is_included} for {file_path}")

            return is_included

        def create_file_node(file_path, full_path, config):
            """Create a file node with correct inclusion status."""
            included = is_file_included(file_path, config)

            try:
                size = os.path.getsize(full_path)
            except OSError:
                logger.warning(f"Could not get size for {full_path}")
                size = 0

            node = {
                'name': os.path.basename(file_path),
                'size': size,
                'included': included,
                'type': 'file'
            }

            logger.debug(f"Created file node: {file_path} (included: {included})")
            return node

        def create_directory_tree(files, config, project_root):
            """Create directory tree with all files and their correct inclusion status."""
            dir_tree = {}

            for file_path, _ in files.items():
                full_path = os.path.join(project_root, file_path)
                if not os.path.exists(full_path):
                    continue

                # Split path into components
                parts = file_path.split('/')
                current = dir_tree

                # Create directory hierarchy
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {
                            'type': 'directory',
                            'children': {}
                        }
                    current = current[part]['children']

                # Add file at the leaf
                last_part = parts[-1]
                current[last_part] = create_file_node(file_path, full_path, config)

            return dir_tree

        def convert_to_treemap(tree, parent_node):
            """Convert directory tree to treemap format while preserving inclusion status."""
            result = []

            for name, content in tree.items():
                if content.get('type') == 'file':
                    # File node - directly add with its inclusion status
                    node = {
                        'name': name,
                        'size': content['size'],
                        'included': content['included'],
                        'type': 'file'
                    }
                    result.append(node)
                    logger.debug(f"Added file node to treemap: {name} (included: {content['included']})")
                else:
                    # Directory node - process children
                    dir_node = {
                        'name': name,
                        'children': [],
                        'type': 'directory'
                    }

                    # Process children
                    dir_node['children'] = convert_to_treemap(content['children'], dir_node)

                    # Directory is included if any child is included
                    dir_node['included'] = any(
                        child.get('included', False)
                        for child in dir_node['children']
                    )

                    result.append(dir_node)
                    logger.debug(f"Added directory node to treemap: {name} (included: {dir_node['included']})")

            return result

        # Process main project files
        main_node = root['children'][0]
        main_config = ref_manager._get_project_config(active_project)
        logger.debug("\nProcessing main project files with config:")
        logger.debug(json.dumps(main_config, indent=2))

        if 'main' in files_by_project:
            dir_tree = create_directory_tree(
                files_by_project['main'],
                main_config,
                project_roots['main']
            )
            main_node['children'] = convert_to_treemap(dir_tree, main_node)
            main_node['included'] = any(
                child.get('included', False)
                for child in main_node['children']
            )

        # Process referenced projects
        ref_node = root['children'][1]
        ref_node['children'] = []
        ref_projects = ref_manager.get_referenced_projects(active_project)

        for project_id, files in files_by_project.items():
            if project_id == 'main':
                continue

            try:
                # Get project configuration
                config_path = ref_projects[project_id]
                with open(config_path, 'r') as f:
                    ref_config = json.load(f)

                project_root = project_roots['referenced'].get(project_id)
                if not project_root:
                    continue

                # Create project node
                project_node = {
                    'name': project_id,
                    'children': [],
                    'type': 'project'
                }

                # Process project files
                dir_tree = create_directory_tree(files, ref_config, project_root)
                project_node['children'] = convert_to_treemap(dir_tree, project_node)

                # Project is included if any child is included
                project_node['included'] = any(
                    child.get('included', False)
                    for child in project_node['children']
                )

                ref_node['children'].append(project_node)

            except Exception as e:
                logger.error(f"Error processing referenced project {project_id}: {str(e)}")

        # Set referenced node inclusion based on children
        ref_node['included'] = any(
            child.get('included', False)
            for child in ref_node['children']
        )

        # Set root inclusion based on children
        root['included'] = any(
            child.get('included', False)
            for child in root['children']
        )

        return root

    def handle_projects(self):
            """Handle request for project list."""
            try:
                projects = self.config.get_projects()
                active_project_path, _ = self.config.get_active_project()

                response = {
                    'projects': [
                        {'path': project_path, 'id': project_id}
                        for project_path, project_id in projects.items()
                    ],
                    'activeProject': active_project_path
                }

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            except Exception as e:
                logger.error(f"Error processing projects request: {str(e)}")
                self.send_error_response(500, str(e))

    def handle_file_content(self, query_params):
        """Handle request for file content."""
        try:
            file_path = query_params.get('path', [''])[0]
            if not file_path:
                self.send_error_response(400, "Missing file path parameter")
                return

            logger.debug(f"[File Request] Original file path: {file_path}")

            # Split path to determine project type
            path_parts = file_path.split('/')
            logger.debug(f"[File Request] Path parts: {path_parts}")

            if len(path_parts) < 2:
                self.send_error_response(400, "Invalid file path structure")
                return

            # Get project root
            project_root = self.config.get_project_root()
            logger.debug(f"[File Request] Project root: {project_root}")

            if not project_root:
                self.send_error_response(500, "Project root not found")
                return

            claudesync_dir = Path(project_root) / ".claudesync"
            if not claudesync_dir.exists():
                self.send_error_response(500, "No .claudesync directory found")
                return

            try:
                full_path = None
                if path_parts[0] == 'main':
                    # Main project files
                    relative_path = '/'.join(path_parts[1:])  # Remove 'main' prefix
                    full_path = os.path.join(project_root, relative_path)
                    logger.debug(f"[File Request] Main project path resolution:")
                    logger.debug(f"  - Project root: {project_root}")
                    logger.debug(f"  - Relative path: {relative_path}")
                    logger.debug(f"  - Full path: {full_path}")

                elif path_parts[0] == 'referenced' and len(path_parts) >= 3:
                    # Referenced project files
                    project_id = path_parts[1]
                    logger.debug(f"[File Request] Referenced project ID: {project_id}")

                    # Use the existing reference manager with the correct config directory
                    ref_manager = ProjectReferencesManager(claudesync_dir)
                    active_project = self.get_active_project()
                    referenced_projects = ref_manager.get_referenced_projects(active_project)

                    if project_id not in referenced_projects:
                        logger.warning(
                            f"[File Request] Project ID {project_id} not found in referenced projects")
                        self.send_error_response(404, f"Referenced project not found: {project_id}")
                        return

                    # Get the project root for the referenced project
                    referenced_root = referenced_projects[project_id].parent.parent
                    relative_path = '/'.join(path_parts[2:])  # Remove 'referenced/project_id' prefix
                    full_path = os.path.join(referenced_root, relative_path)
                    logger.debug(f"[File Request] Referenced project path resolution:")
                    logger.debug(f"  - Referenced root: {referenced_root}")
                    logger.debug(f"  - Relative path: {relative_path}")
                    logger.debug(f"  - Full path: {full_path}")

                else:
                    logger.debug(f"[File Request] Invalid path structure. First part: {path_parts[0]}")
                    self.send_error_response(400, f"Invalid path structure: {file_path}")
                    return

                logger.debug(f"[File Request] Final full path: {full_path}")
                logger.debug(f"[File Request] Path exists: {os.path.exists(full_path) if full_path else False}")
                logger.debug(f"[File Request] Is file: {os.path.isfile(full_path) if full_path else False}")

                # Read and return file content
                if not full_path or not os.path.exists(full_path) or not os.path.isfile(full_path):
                    self.send_error_response(404, f"File not found: {full_path}")
                    return

                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.debug(f"[File Request] Successfully read file content")

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    'content': content,
                    'path': file_path
                }).encode())

            except Exception as e:
                logger.error(f"[File Request] Error reading file {file_path}: {str(e)}")
                self.send_error_response(500, f"Error reading file: {str(e)}")

        except Exception as e:
            logger.error(f"[File Request] Error handling file content request: {str(e)}")
            self.send_error_response(500, str(e))

    def get_active_project(self) -> Optional[str]:
        """Get the path of the active project."""
        active_project_path, _ = self.config.get_active_project()
        return active_project_path

    def send_error_response(self, status_code: int, message: str):
        """Send error response with given status code and message."""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({
            'error': message
        }).encode())

    def get_stats(self, files_by_project):
        """Calculate statistics for files across all projects."""
        stats = {
            'total_files': 0,
            'total_size': 0,
            'projects': {}
        }

        for project_id, files in files_by_project.items():
            project_size = 0
            for file_path in files:
                try:
                    size = os.path.getsize(file_path)
                    project_size += size
                    stats['total_size'] += size
                    stats['total_files'] += 1
                except OSError:
                    continue

            stats['projects'][project_id] = {
                'files': len(files),
                'size': project_size
            }

        return stats

def start_simulation_server(web_dir: str, port: int, no_browser: bool, config):
    """Start the HTTP server for visualization."""
    os.chdir(web_dir)

    class LocalhostTCPServer(socketserver.TCPServer):
        def server_bind(self):
            self.socket.setsockopt(socketserver.socket.SOL_SOCKET, socketserver.socket.SO_REUSEADDR, 1)
            self.socket.bind(('127.0.0.1', self.server_address[1]))

    handler = lambda *args: SyncDataHandler(*args, config=config)

    try:
        with LocalhostTCPServer(("127.0.0.1", port), handler) as httpd:
            url = f"http://localhost:{port}"
            click.echo(f"Server started at {url}")

            if not no_browser:
                webbrowser.open(url)

            click.echo("Press Ctrl+C to stop the server...")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                click.echo("\nShutting down server...")
                httpd.shutdown()
                httpd.server_close()

    except OSError as e:
        if e.errno == 98:  # Address already in use
            click.echo(f"Error: Port {port} is already in use. Try a different port with --port option.")
        else:
            click.echo(f"Error: Failed to start server: {e}")

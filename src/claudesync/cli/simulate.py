import traceback

import click
import logging
import os
import json
import http.server
import socketserver
import webbrowser
import threading
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from pathspec import pathspec

from ..exceptions import ConfigurationError
from ..utils import get_local_files, load_gitignore, load_claudeignore, FileInfo, FileSource
from ..configmanager import FileConfigManager
from typing import Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class TreeNode(TypedDict):
    name: str
    size: Optional[int]
    path: str
    children: Optional[List['TreeNode']]
    included: Optional[bool]

def build_file_tree(files_to_sync: Dict[str, FileInfo], config) -> dict:
    """
    Build a hierarchical tree structure from the list of files.
    """
    # Create root structure with main and referenced sections
    root = {
        'name': 'root',
        'children': [
            {'name': 'main', 'children': [], 'included': True},
            {'name': 'referenced', 'children': [], 'included': True}
        ]
    }

    # Get active project and its config
    active_project = config.get_active_project()[0]
    files_config = config.get_files_config(active_project)
    reference_paths = config._get_reference_paths(active_project)

    # Group files by source and project
    main_files = {}
    referenced_projects = {}

    logger.debug("Starting to group files by source and project")
    for path, file_info in files_to_sync.items():
        if file_info.source == FileSource.MAIN:
            main_files[path] = file_info
        else:
            project_id = file_info.project_id or 'unknown'
            if project_id not in referenced_projects:
                referenced_projects[project_id] = {}
            referenced_projects[project_id][path] = file_info

    def add_to_tree(file_path: str, file_info: FileInfo, parent_node: dict):
        path_parts = Path(file_path).parts
        current = parent_node

        # Build directory structure
        for i, part in enumerate(path_parts[:-1]):
            child = next((c for c in current['children'] if c['name'] == part), None)
            if child is None:
                child = {
                    'name': part,
                    'children': [],
                    'included': True  # Directories are always shown
                }
                current['children'].append(child)
            current = child

        # Get file size from root path
        try:
            file_size = os.path.getsize(os.path.join(file_info.root_path, file_path))
        except OSError:
            file_size = 0

        # Add file node with inclusion status from FileInfo
        current['children'].append({
            'name': path_parts[-1],
            'size': file_size,
            'included': file_info.included
        })

    # Process main project files
    main_node = root['children'][0]
    for path, file_info in main_files.items():
        add_to_tree(path, file_info, main_node)

    # Process referenced projects
    referenced_node = root['children'][1]

    # Get all referenced projects from configuration
    references = files_config.get('references', [])

    # Create nodes for each referenced project, even if no files
    for ref_id in references:
        if ref_id not in referenced_projects:
            referenced_projects[ref_id] = {}  # Empty dict for projects with no files

    # Process referenced projects
    for project_id, project_files in referenced_projects.items():
        logger.debug(f"Processing referenced project {project_id}")

        # Create project node
        project_node = {
            'name': project_id,
            'children': [],
            'included': True  # Project nodes are always shown
        }
        referenced_node['children'].append(project_node)

        # Add files for this project
        for path, file_info in project_files.items():
            add_to_tree(path, file_info, project_node)

    # Add placeholders only if no referenced projects are configured
    if not references:
        referenced_node['children'].append({
            'name': 'No referenced projects',
            'size': 0,
            'included': False
        })
    elif not referenced_node['children']:
        # If we have references but no files, show empty project nodes
        for ref_id in references:
            referenced_node['children'].append({
                'name': ref_id,
                'children': [],
                'included': True
            })

    return root

def process_root(root_dir: str, rel_root_base: str, node: dict, sync_files: set,
                 gitignore: Optional[pathspec.PathSpec], claudeignore: Optional[pathspec.PathSpec]):
    """
    Process a single root directory and build its tree structure.

    Args:
        root_dir: The full path to the root directory
        rel_root_base: The relative path base for this root
        node: The node to populate with the tree structure
        sync_files: Set of files that will be synced
        gitignore: PathSpec object for gitignore patterns
        claudeignore: PathSpec object for claudeignore patterns
    """
    for current_dir, _, files in os.walk(root_dir):
        # Get path relative to the project root
        rel_root = os.path.relpath(current_dir, root_dir)
        rel_root = '' if rel_root == '.' else rel_root

        # Skip ignored directories
        full_rel_path = os.path.join(rel_root_base, rel_root) if rel_root_base else rel_root
        if (gitignore and gitignore.match_file(full_rel_path)) or \
                (claudeignore and claudeignore.match_file(full_rel_path)):
            continue

        for filename in files:
            rel_path = os.path.join(full_rel_path, filename)
            full_path = os.path.join(current_dir, filename)

            # Skip if file doesn't exist anymore or is ignored
            if not os.path.exists(full_path) or \
                    (claudeignore and claudeignore.match_file(rel_path)):
                continue

            # Get file size
            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                continue

            # Build path in tree
            current = node
            path_parts = Path(rel_path).parts

            # Navigate/build the tree structure
            for i, part in enumerate(path_parts[:-1]):
                # Find or create directory node
                child = next((c for c in current['children'] if c['name'] == part), None)
                if child is None:
                    child = {
                        'name': part,
                        'children': []
                    }
                    current['children'].append(child)
                current = child

            # Add the file node
            current['children'].append({
                'name': path_parts[-1],
                'size': file_size,
                'included': rel_path in sync_files
            })

def get_project_root():
    """Get the project root directory."""
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    logger.debug(f"Project root directory: {project_root}")
    return project_root

def load_claudeignore_as_string(config):
    """Load .claudeignore content from local project directory."""
    local_path = config.get_local_path()
    logger.debug(f"Loading .claudeignore from local path: {local_path}")

    if not local_path:
        logger.warning("No local path found in config")
        return ""

    claudeignore_path = Path(local_path) / '.claudeignore'
    logger.debug(f"Attempting to load .claudeignore from: {claudeignore_path}")

    try:
        with open(claudeignore_path, 'r') as f:
            content = f.read().strip()
            logger.debug(f"Successfully loaded .claudeignore with content length: {len(content)}")
            return content
    except FileNotFoundError:
        logger.warning(f".claudeignore file not found at {claudeignore_path}")
        return ""
    except Exception as e:
        logger.error(f"Error reading .claudeignore at {claudeignore_path}: {e}")
        return ""

def is_safe_path(base_dir: str, requested_path: str) -> bool:
    """
    Safely verify that the requested path is within the base directory.
    """
    try:
        # Resolve any symlinks and normalize path
        base_dir = os.path.realpath(base_dir)
        requested_path = os.path.realpath(os.path.join(base_dir, requested_path))

        # Check if the resolved path starts with the base directory
        common_prefix = os.path.commonpath([requested_path, base_dir])
        return common_prefix == base_dir
    except (ValueError, OSError):
        # Handle any path manipulation errors
        return False

def load_config():
    """Load configuration from .claudesync/config.local.json."""
    project_root = get_project_root()
    config_path = project_root / '.claudesync' / 'config.local.json'
    logger.debug(f"Attempting to load config from: {config_path}")

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            categories = config.get('file_categories', {})
            logger.debug(f"Successfully loaded config with {len(categories)} categories: {list(categories.keys())}")
            return categories
    except FileNotFoundError:
        logger.warning(f"Config file not found at {config_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file at {config_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading config file at {config_path}: {e}")
        return {}

def format_size(size):
    """Convert size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def get_root_path(file_info: FileInfo, config, reference_paths: Dict[str, str] = None) -> str:
    """
    Get the correct root path for a file based on its source.

    Args:
        file_info: FileInfo object containing file metadata
        config: Configuration manager instance
        reference_paths: Dictionary mapping reference IDs to their paths

    Returns:
        str: The root path for the file
    """
    if file_info.source == FileSource.MAIN:
        return config.get_project_root()

    if file_info.source == FileSource.REFERENCED and file_info.project_id:
        if not reference_paths:
            # Get reference paths if not provided
            active_project = config.get_active_project()[0]
            reference_paths = config._get_reference_paths(active_project)

        if file_info.project_id in reference_paths:
            ref_path = Path(reference_paths[file_info.project_id])
            return str(ref_path.parent.parent)  # Move up from .claudesync/config.json

    # Fallback to main project root
    return config.get_project_root()

def display_file_list(files: Dict[str, FileInfo], config) -> None:
    """Display a formatted list of files that would be synchronized."""
    if not files:
        click.echo("No files would be synchronized.")
        return

    # Get active project and reference paths
    active_project = config.get_active_project()[0]
    reference_paths = config._get_reference_paths(active_project) if active_project else {}

    # Group files by source
    main_files = []
    referenced_files = {}

    for path, file_info in files.items():
        if file_info.source == FileSource.MAIN:
            main_files.append((path, file_info))
        else:
            project_id = file_info.project_id or "unknown"
            if project_id not in referenced_files:
                referenced_files[project_id] = []
            referenced_files[project_id].append((path, file_info))

    # Calculate totals using get_root_path
    total_files = len(files)
    total_size = 0

    # Display main project files
    click.echo("\nMain Project Files:")
    click.echo("=" * 80)
    if main_files:
        for path, file_info in sorted(main_files):
            try:
                root_path = get_root_path(file_info, config, reference_paths)
                full_path = os.path.join(root_path, path)
                size = os.path.getsize(full_path)
                total_size += size
                click.echo(f"{path:<60} {format_size(size):>10}")
            except OSError as e:
                logger.error(f"Error accessing file {path}: {e}")
                click.echo(f"{path:<60} {'ERROR':>10}")
    else:
        click.echo("No files from main project")

    # Display referenced project files
    if referenced_files:
        for project_id, files_list in referenced_files.items():
            click.echo(f"\nReferenced Project: {project_id}")
            click.echo("=" * 80)
            for path, file_info in sorted(files_list):
                try:
                    root_path = get_root_path(file_info, config, reference_paths)
                    full_path = os.path.join(root_path, path)
                    size = os.path.getsize(full_path)
                    total_size += size
                    click.echo(f"{path:<60} {format_size(size):>10}")
                except OSError as e:
                    logger.error(f"Error accessing file {path}: {e}")
                    click.echo(f"{path:<60} {'ERROR':>10}")

    # Display summary
    click.echo("\nSummary:")
    click.echo("=" * 80)
    click.echo(f"Total files: {total_files}")
    click.echo(f"Total size: {format_size(total_size)}")
    click.echo(f"Main project files: {len(main_files)}")
    for project_id, files_list in referenced_files.items():
        click.echo(f"Referenced project {project_id}: {len(files_list)} files")


class SyncDataHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, config=None, **kwargs):
        self.config = config
        super().__init__(*args, **kwargs)

    def get_active_project(self):
        """Get the currently active project path"""
        active_project_path, active_project_id = self.config.get_active_project()
        if not active_project_path:
            raise ConfigurationError("No active project found")
        return active_project_path

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        logger.debug(f"Handling POST request for path: {parsed_path.path}")

        if parsed_path.path == '/api/set-active-project':
            content_length = int(self.headers.get('Content-Length', 0))
            request_body = self.rfile.read(content_length)

            try:
                data = json.loads(request_body)
                project_path = data.get('path')

                if not project_path:
                    raise ValueError("Project path is required")

                # Verify the project exists
                project_id = self.config.get_project_id(project_path)
                if not project_id:
                    raise ValueError(f"Project not found: {project_path}")

                # Set the active project
                self.config.set_active_project(project_path, project_id)
                self.project = project_path  # Update handler's project reference

                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Active project set to: {project_path}'
                }).encode())

                logger.debug(f"Successfully set active project to: {project_path}")

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in request body: {e}")
                self._send_error_response(400, "Invalid JSON in request body")
            except ValueError as e:
                logger.error(f"Invalid request: {str(e)}")
                self._send_error_response(400, str(e))
            except Exception as e:
                logger.error(f"Error setting active project: {str(e)}\n{traceback.format_exc()}")
                self._send_error_response(500, f"Internal server error: {str(e)}")

            return

        # Handle other POST requests (if any)
        self._send_error_response(404, "Not Found")

    def _send_error_response(self, status_code: int, message: str):
        """Helper method to send error responses"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({
            'success': False,
            'error': message
        }).encode())

    def do_GET(self):
        parsed_path = urlparse(self.path)
        logger.debug(f"Handling GET request for path: {parsed_path.path}")

        if parsed_path.path.startswith('/api/file-content'):
            try:
                # Parse the file path from query parameters
                query_params = parse_qs(parsed_path.query)
                file_path = query_params.get('path', [''])[0]

                if not file_path:
                    self._send_error_response(400, "Missing file path parameter")
                    return

                # Get current config and project root
                project_root = self.config.get_project_root()

                # Validate the requested path is within project root for security
                full_path = os.path.join(project_root, file_path)
                if not is_safe_path(project_root, file_path):
                    self._send_error_response(403, "Access denied - path is outside project root")
                    return

                # Check if file exists
                if not os.path.exists(full_path) or not os.path.isfile(full_path):
                    self._send_error_response(404, "File not found")
                    return

                # Read and return file content
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'content': content,
                        'path': file_path
                    }).encode())

                except UnicodeDecodeError:
                    self._send_error_response(400, "File is not valid UTF-8 text")
                except IOError as e:
                    self._send_error_response(500, f"Error reading file: {str(e)}")

            except Exception as e:
                logger.error(f"Error processing file content request: {str(e)}\n{traceback.format_exc()}")
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        if parsed_path.path == '/api/sync-data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()

            try:
                local_path = self.config.get_project_root()
                active_project = self.get_active_project()
                files_config = self.config.get_files_config(active_project)

                # Get files that would be synced based on project configuration
                files_to_sync = get_local_files(self.config, local_path, files_config)

                # Build response data
                response_data = {
                    'claudeignore': load_claudeignore_as_string(self.config),
                    'project': files_config,
                    'stats': self._get_stats(local_path, files_to_sync),
                    'treemap': self._get_treemap(local_path, files_to_sync, self.config, files_config)
                }

                self.wfile.write(json.dumps(response_data).encode())
            except Exception as e:
                logger.error(f"Error processing sync data request: {str(e)}\n{traceback.format_exc()}")
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        if parsed_path.path == '/api/projects':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()

            try:
                # Get all projects, including unlinked ones
                projects = self.config.get_projects(include_unlinked=True)
                active_project_path, active_project_id = self.config.get_active_project()

                response = {
                    'projects': [
                        {
                            'id': project_id if project_id else '',  # Empty string for unlinked projects
                            'path': project_path,
                            'linked': bool(project_id)  # True if project has an ID
                        }
                        for project_path, project_id in projects.items()
                    ],
                    'activeProject': active_project_path
                }

                self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                logger.error(f"Error getting projects: {str(e)}\n{traceback.format_exc()}")
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        # For all other paths, serve static files
        return super().do_GET()

    def _get_stats(self, local_path, files_to_sync):
        """Calculate sync statistics"""
        total_size = 0
        total_files = 0

        for file_path in files_to_sync:
            full_path = os.path.join(local_path, file_path)
            if os.path.exists(full_path):
                size = os.path.getsize(full_path)
                total_size += size
                total_files += 1

        return {
            "filesToSync": total_files,
            "totalSize": format_size(total_size)
        }

    def _get_treemap(self, local_path, files_to_sync, config, files_config):
        """Generate treemap data"""
        tree = build_file_tree(files_to_sync, config)
        return tree

@click.command()
@click.option('--port', default=4201, help='Port to run the server on')
@click.option('--no-browser', is_flag=True, help='Do not open browser automatically')
@click.option('--list', 'show_list', is_flag=True, help='Show list of files to be synchronized')
@click.pass_obj
def simulate_push(config, port, no_browser, show_list):
    """Simulate file synchronization and optionally display file list."""
    try:
        # Get active project configuration
        active_project = config.get_active_project()[0]
        if not active_project:
            raise ConfigurationError("No active project found")

        files_config = config.get_files_config(active_project)
        project_root = config.get_project_root()

        # Get files that would be synced
        files_to_sync = get_local_files(config, project_root, files_config)

        if show_list:
            # Display file list and exit
            display_file_list(files_to_sync, config)
            return

        # Continue with visualization server
        web_dir = os.path.join(os.path.dirname(__file__), '../web/dist/claudesync-simulate')
        logger.debug(f"Web directory path: {web_dir}")

        if not os.path.exists(web_dir):
            logger.error(f"Web directory does not exist: {web_dir}")
            click.echo(f"Error: Web directory not found at {web_dir}")
            return

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
                click.echo(f"Simulating sync for active project: {active_project}")

                if not no_browser:
                    webbrowser.open(url)

                click.echo("Press Ctrl+C to stop the server...")
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    logger.debug("Received KeyboardInterrupt, shutting down server")
                    click.echo("\nShutting down server...")
                    httpd.shutdown()
                    httpd.server_close()
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.error(f"Port {port} is already in use")
                click.echo(f"Error: Port {port} is already in use. Try a different port with --port option.")
            else:
                logger.error(f"Failed to start server: {e}")
                click.echo(f"Error: Failed to start server: {e}")

    except ConfigurationError as e:
        click.echo(f"Error: {str(e)}")
        return
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        click.echo(f"Error: An unexpected error occurred: {str(e)}")
        return

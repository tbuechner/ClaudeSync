import functools
import os
import time
import logging
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Dict, Optional

from tqdm import tqdm

from .utils import compute_md5_hash
from .exceptions import ProviderError, ConfigurationError
from .compression import compress_content, decompress_content
from .project_references_manager import ProjectReferencesManager

logger = logging.getLogger(__name__)

def retry_on_403(max_retries=3, delay=1):
    """Decorator to retry operations that fail with 403 errors."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            self = args[0] if len(args) > 0 else None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ProviderError as e:
                    if "403 Forbidden" in str(e) and attempt < max_retries - 1:
                        if self and hasattr(self, "logger"):
                            self.logger.warning(
                                f"Received 403 error. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                            )
                        else:
                            logger.warning(
                                f"Received 403 error. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                            )
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

class SyncManager:
    """Manages synchronization of files between local filesystem and remote provider."""

    def __init__(self, provider, config, project_id: str, local_path: Path):
        """Initialize the SyncManager with provider and configuration."""
        self.provider = provider
        self.config = config
        self.active_organization_id = config.get("active_organization_id")
        self.active_project_id = project_id
        self.local_path = local_path
        self.upload_delay = config.get("upload_delay", 0.5)
        self.two_way_sync = config.get("two_way_sync", False)
        self.max_retries = 3
        self.retry_delay = 1
        self.compression_algorithm = config.get("compression_algorithm", "none")
        self.synced_files = {}  # Track synced files and their info

        # Initialize references manager
        self.ref_manager = ProjectReferencesManager()

    def sync(self, local_files: Dict[str, str], remote_files: list):
        """
        Synchronize local files with remote project.

        Args:
            local_files: Dictionary mapping file paths to their hashes or file info
            remote_files: List of remote file objects from the API
        """
        self.synced_files = {}  # Reset synced files tracking

        if self.compression_algorithm == "none":
            self._sync_without_compression(local_files, remote_files)
        else:
            self._sync_with_compression(local_files, remote_files)

    def _sync_without_compression(self, local_files: Dict[str, str], remote_files: list):
        """Sync files without using compression."""
        # Initialize tracking sets
        remote_files_to_delete = set(rf["file_name"] for rf in remote_files)
        synced_files = set()

        logger.debug(f"Initial remote_files_to_delete: {remote_files_to_delete}")
        logger.debug(f"Total local files: {len(local_files)}")
        logger.debug(f"Total remote files: {len(remote_files)}")

        # Sync local → remote
        with tqdm(total=len(local_files), desc="Local → Remote") as pbar:
            for local_file, file_info in local_files.items():
                # Handle both simple hash strings and dictionary file info
                local_hash = file_info if isinstance(file_info, str) else file_info.get('hash')
                file_root = file_info.get('root_path', self.local_path) if isinstance(file_info, dict) else self.local_path

                remote_file = next(
                    (rf for rf in remote_files if rf["file_name"] == local_file), None
                )

                if remote_file:
                    self.update_existing_file(
                        local_file,
                        local_hash,
                        remote_file,
                        remote_files_to_delete,
                        synced_files,
                        file_root
                    )
                else:
                    self.upload_new_file(local_file, synced_files, file_root)
                pbar.update(1)

        # Update local timestamps to match remote
        self.update_local_timestamps(remote_files, synced_files)

        # # Two-way sync if enabled
        if self.two_way_sync:
            with tqdm(total=len(remote_files), desc="Local ← Remote") as pbar:
                for remote_file in remote_files:
                    self.sync_remote_to_local(
                        remote_file, remote_files_to_delete, synced_files
                    )
                    pbar.update(1)

        # Delete files that only exist remotely
        self.prune_remote_files(remote_files, remote_files_to_delete)

    def _sync_with_compression(self, local_files, remote_files):
        """Sync files using compression."""
        packed_content = self._pack_files(local_files)
        compressed_content = compress_content(packed_content, self.compression_algorithm)

        remote_file_name = f"claudesync_packed_{datetime.now().strftime('%Y%m%d%H%M%S')}.dat"
        self._upload_compressed_file(compressed_content, remote_file_name)

        if self.two_way_sync:
            remote_compressed_content = self._download_compressed_file()
            if remote_compressed_content:
                remote_packed_content = decompress_content(
                    remote_compressed_content, self.compression_algorithm
                )
                self._unpack_files(remote_packed_content)

        self._cleanup_old_remote_files(remote_files)

    def _pack_files(self, local_files):
        """Pack multiple files into a single content stream."""
        packed_content = io.StringIO()
        for file_path, file_hash in local_files.items():
            full_path = os.path.join(self.local_path, file_path)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            packed_content.write(f"--- BEGIN FILE: {file_path} ---\n")
            packed_content.write(content)
            packed_content.write(f"\n--- END FILE: {file_path} ---\n")
        return packed_content.getvalue()

    @retry_on_403()
    def _upload_compressed_file(self, compressed_content, file_name):
        """Upload a compressed file to the remote project."""
        logger.debug(f"Uploading compressed file {file_name} to remote...")
        self.provider.upload_file(
            self.active_organization_id,
            self.active_project_id,
            file_name,
            compressed_content,
        )
        time.sleep(self.upload_delay)

    @retry_on_403()
    def _download_compressed_file(self):
        """Download the latest compressed file from remote."""
        logger.debug("Downloading latest compressed file from remote...")
        remote_files = self.provider.list_files(
            self.active_organization_id, self.active_project_id
        )
        compressed_files = [
            rf for rf in remote_files
            if rf["file_name"].startswith("claudesync_packed_")
        ]
        if compressed_files:
            latest_file = max(compressed_files, key=lambda x: x["file_name"])
            return latest_file["content"]
        return None

    def _unpack_files(self, packed_content):
        """Unpack a packed content stream into individual files."""
        current_file = None
        current_content = io.StringIO()

        for line in packed_content.splitlines():
            if line.startswith("--- BEGIN FILE:"):
                if current_file:
                    self._write_file(current_file, current_content.getvalue())
                    current_content = io.StringIO()
                current_file = line.split("--- BEGIN FILE:")[1].strip()
            elif line.startswith("--- END FILE:"):
                if current_file:
                    self._write_file(current_file, current_content.getvalue())
                    current_file = None
                    current_content = io.StringIO()
            else:
                current_content.write(line + "\n")

        if current_file:
            self._write_file(current_file, current_content.getvalue())

    def _write_file(self, file_path, content):
        """Write content to a local file."""
        full_path = os.path.join(self.local_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _cleanup_old_remote_files(self, remote_files):
        """Clean up old compressed files from remote."""
        for remote_file in remote_files:
            if remote_file["file_name"].startswith("claudesync_packed_"):
                self.provider.delete_file(
                    self.active_organization_id,
                    self.active_project_id,
                    remote_file["uuid"],
                )

    def update_existing_file(self, local_file: str, local_hash: str, remote_file: dict,
                           remote_files_to_delete: set, synced_files: set, file_root: Path):
        """Update an existing file if it has changed."""
        remote_content = remote_file["content"]
        remote_hash = compute_md5_hash(remote_content)

        if local_hash != remote_hash:
            logger.debug(f"Different local and remote hash...")
            with tqdm(total=2, desc=f"Updating {local_file}", leave=False) as pbar:
                logger.debug(f"Deleting remote file... {local_file}")

                self.provider.delete_file(
                    self.active_organization_id,
                    self.active_project_id,
                    remote_file["uuid"],
                )
                pbar.update(1)

                # Convert file_root Path to string if it's a Path object
                file_root = str(file_root) if isinstance(file_root, Path) else file_root

                # Construct full path properly using os.path.join
                full_path = os.path.join(file_root, local_file)

                try:
                    with open(full_path, "r", encoding="utf-8") as file:
                        content = file.read()

                    logger.debug(f"Uploading local file... {local_file}")

                    self.provider.upload_file(
                        self.active_organization_id,
                        self.active_project_id,
                        local_file,
                        content,
                    )
                    pbar.update(1)
                    time.sleep(self.upload_delay)
                    synced_files.add(local_file)
                except Exception as e:
                    logger.error(f"Error processing file {full_path}: {str(e)}")
                    raise
        logger.debug(f"Skipping upload of local file... {local_file}")
        remote_files_to_delete.remove(local_file)


    def upload_new_file(self, local_file: str, synced_files: set, file_root: Path):
        """Upload a new file to remote."""
        logger.debug(f"Uploading new file to remote... {local_file}")

        # Convert file_root Path to string if it's a Path object
        file_root = str(file_root) if isinstance(file_root, Path) else file_root

        # Construct full path properly using os.path.join
        full_path = os.path.join(file_root, local_file)

        try:
            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()

            with tqdm(total=1, desc=f"Uploading {local_file}", leave=False) as pbar:
                self.provider.upload_file(
                    self.active_organization_id,
                    self.active_project_id,
                    local_file,
                    content,
                )
                pbar.update(1)
            time.sleep(self.upload_delay)
            synced_files.add(local_file)
        except Exception as e:
            logger.error(f"Error processing file {full_path}: {str(e)}")
            raise

    def update_local_timestamps(self, remote_files: list, synced_files: set):
        """Update timestamps of local files to match remote timestamps."""
        logger.debug("Updating local file timestamps...")
        for remote_file in remote_files:
            file_name = remote_file["file_name"]
            if file_name in synced_files:
                try:
                    # Convert remote timestamp to local time
                    remote_timestamp = datetime.strptime(
                        remote_file["created_at"],
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).replace(tzinfo=timezone.utc).timestamp()

                    # Get the file path considering root paths from referenced projects
                    local_path = None
                    if isinstance(self.synced_files.get(file_name), dict):
                        root_path = self.synced_files[file_name].get('root_path', self.local_path)
                        local_path = os.path.join(root_path, file_name)
                    else:
                        local_path = os.path.join(self.local_path, file_name)

                    if local_path and os.path.exists(local_path):
                        os.utime(local_path, (remote_timestamp, remote_timestamp))
                        logger.debug(f"Updated timestamp for {file_name}")
                except (ValueError, OSError) as e:
                    logger.warning(f"Failed to update timestamp for {file_name}: {str(e)}")
                    continue

    def sync_remote_to_local(self, remote_file: dict, remote_files_to_delete: set, synced_files: set):
        """Sync a remote file to local if needed."""
        file_name = remote_file["file_name"]
        if file_name not in synced_files:
            logger.debug(f"Processing remote file {file_name}")
            try:
                local_path = os.path.join(self.local_path, file_name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(remote_file["content"])

                remote_timestamp = datetime.strptime(
                    remote_file["created_at"],
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=timezone.utc).timestamp()
                os.utime(local_path, (remote_timestamp, remote_timestamp))

                synced_files.add(file_name)
            except Exception as e:
                logger.error(f"Error syncing remote file {file_name}: {str(e)}")

    def prune_remote_files(self, remote_files: list, remote_files_to_delete: set):
        """Delete files from remote that don't exist locally."""
        if not self.config.get("prune_remote_files"):
            logger.info("Remote pruning is not enabled.")
            return

        logger.debug(f"Files to delete: {remote_files_to_delete}")
        for file_to_delete in list(remote_files_to_delete):
            try:
                self.delete_remote_files(file_to_delete, remote_files)
            except StopIteration:
                logger.warning(f"Could not find remote file info for {file_to_delete}")
                continue

    @retry_on_403()
    def delete_remote_files(self, file_to_delete: str, remote_files: list):
        """Delete a file from remote."""
        logger.debug(f"Deleting {file_to_delete} from remote...")
        remote_file = next(
            rf for rf in remote_files if rf["file_name"] == file_to_delete
        )
        with tqdm(total=1, desc=f"Deleting {file_to_delete}", leave=False) as pbar:
            self.provider.delete_file(
                self.active_organization_id,
                self.active_project_id,
                remote_file["uuid"]
            )
            pbar.update(1)
        time.sleep(self.upload_delay)

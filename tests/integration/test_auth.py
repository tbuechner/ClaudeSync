import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from claudesync.cli.main import cli
from claudesync.configmanager import FileConfigManager

class TestAuthIntegration(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        # Create a temporary directory for the test
        self.test_dir = tempfile.mkdtemp()
        self.old_home = os.environ.get('HOME')
        # Set HOME to our test directory so .claudesync is created there
        os.environ['HOME'] = self.test_dir

        # Delete any existing .claudesync folder in current directory
        claudesync_dir = Path(os.getcwd()) / '.claudesync'
        if claudesync_dir.exists():
            shutil.rmtree(claudesync_dir)

        # Create a CLI runner
        self.runner = CliRunner()

        # Ensure we have the required environment variable
        self.session_key = os.environ.get('CLAUDE_SESSION_KEY')
        if not self.session_key:
            raise ValueError("CLAUDE_SESSION_KEY environment variable must be set")

    def tearDown(self):
        """Clean up after each test"""
        # Restore the original HOME
        if self.old_home:
            os.environ['HOME'] = self.old_home
        else:
            del os.environ['HOME']

        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)

    @patch('claudesync.session_key_manager.SessionKeyManager._find_ssh_key')
    def test_01_login_with_session_key(self, mock_find_ssh_key):
        """Test logging in with a session key provided via command line"""

        mock_find_ssh_key.return_value = "/Users/thomasbuechner/.ssh/id_ed25519"

        # Run the login command with the session key
        result = self.runner.invoke(
            cli,
            ['auth', 'login', '--session-key', self.session_key, '--auto-approve']
        )

        if result.exception:
            import traceback
            print(f"Exception during login: {result.exception}")
            print("Full traceback:")
            print(''.join(traceback.format_tb(result.exc_info[2])))
        if result.output:
            print(f"Command output: {result.output}")

        # Check command succeeded
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Successfully authenticated with Claude AI", result.output)

        # Verify config file was created
        config_dir = Path(self.test_dir) / '.claudesync'
        self.assertTrue(config_dir.exists())

        # assert that there is a file called config.json in the config_dir
        config_file = config_dir / 'config.json'
        self.assertTrue(config_file.exists())

        # Verify session key was stored
        config = FileConfigManager()
        stored_key, expiry = config.get_session_key()
        self.assertIsNotNone(stored_key)
        self.assertIsNotNone(expiry)

        # Verify we can use the stored credentials
        result = self.runner.invoke(cli, ['organization', 'ls'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("No organizations", result.output)

    @patch('claudesync.session_key_manager.SessionKeyManager._find_ssh_key')
    def test_02_project_create(self, mock_find_ssh_key):
        """Test creating a new project after successful login"""
        mock_find_ssh_key.return_value = "/Users/thomasbuechner/.ssh/id_ed25519"

        # First ensure we're logged in
        login_result = self.runner.invoke(
            cli,
            ['auth', 'login', '--session-key', self.session_key, '--auto-approve']
        )
        self.assertEqual(login_result.exit_code, 0)

        # Create a new project
        project_result = self.runner.invoke(
            cli,
            ['project', 'create', '--name', 'Test Project', '--internal-name', 'test-project',
             '--description', 'Test project created by integration test', '--no-git-check'],
            input='y\n'  # Automatically confirm any prompts
        )

        if project_result.exception:
            import traceback
            print(f"Exception during project creation: {project_result.exception}")
            print("Full traceback:")
            print(''.join(traceback.format_tb(project_result.exc_info[2])))
        if project_result.output:
            print(f"Command output: {project_result.output}")

        # Check command succeeded
        self.assertEqual(project_result.exit_code, 0)
        self.assertIn("Project", project_result.output)
        self.assertIn("has been created successfully", project_result.output)

        # Verify project files were created
        claudesync_dir = Path(os.getcwd()) / '.claudesync'
        project_config = claudesync_dir / 'test-project.project.json'
        project_id_config = claudesync_dir / 'test-project.project_id.json'
        active_project = claudesync_dir / 'active_project.json'

        self.assertTrue(project_config.exists())
        self.assertTrue(project_id_config.exists())
        self.assertTrue(active_project.exists())

        # Verify project configurations
        with open(project_config) as f:
            config_data = json.load(f)
            self.assertEqual(config_data['project_name'], 'Test Project')
            self.assertEqual(config_data['project_description'], 'Test project created by integration test')
            self.assertIn('includes', config_data)
            self.assertIn('excludes', config_data)

        # Verify project ID was stored
        with open(project_id_config) as f:
            id_data = json.load(f)
            self.assertIn('project_id', id_data)
            self.assertTrue(id_data['project_id'].strip())

        # Verify active project was set
        with open(active_project) as f:
            active_data = json.load(f)
            self.assertEqual(active_data['project_path'], 'test-project')
            self.assertEqual(active_data['project_id'], id_data['project_id'])

if __name__ == '__main__':
    unittest.main()
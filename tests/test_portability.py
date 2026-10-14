import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import load_cursor_key, CursorSDKClient, CursorSDKError

class PortabilityTests(unittest.TestCase):
    def test_key_comes_from_hermes_profile_scope_not_credential_files(self):
        with patch('agent.secret_scope.get_secret', return_value='offline-scoped-key') as secret, patch('pathlib.Path.open', side_effect=AssertionError('credential file read')):
            self.assertEqual(load_cursor_key(), 'offline-scoped-key')
        secret.assert_called_once_with('CURSOR_API_KEY')

if __name__ == '__main__':
    unittest.main()

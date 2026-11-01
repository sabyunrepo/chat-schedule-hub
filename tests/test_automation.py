import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from hub.site_access import service_token
from hub.push import allowed_endpoint, public_key

class AutomationTests(unittest.TestCase):
 def test_site_keychain_is_origin_bound_and_no_secret_in_argv(self):
  with patch('hub.site_access.subprocess.run',return_value=Mock(returncode=0,stdout=b'secret-value')) as run:
   self.assertEqual(service_token('https://example.chatgpt.site',Path('/helper')),'secret-value')
   self.assertEqual(run.call_args.args[0],['/helper','get','https://example.chatgpt.site'])
  for origin in ['http://example.com','https://user:pw@example.com','https://example.com/path']:
   with self.assertRaises(ValueError):service_token(origin)
 def test_keychain_failure_never_returns_error_text_as_token(self):
  with patch('hub.site_access.subprocess.run',return_value=Mock(returncode=1,stdout=b'private')):
   with self.assertRaises(RuntimeError):service_token('https://example.com')
 def test_push_ssrf_validation(self):
  for url in ['http://fcm.googleapis.com','https://localhost','https://jmt17.google.com.evil.test/fcm/send/x','https://jmt17.google.com/other','https://fcm.googleapis.com.evil.test','https://x:pw@fcm.googleapis.com']:
   self.assertFalse(allowed_endpoint(url))
  self.assertTrue(allowed_endpoint('https://web.push.apple.com/123'))
  self.assertTrue(allowed_endpoint('https://jmt17.google.com/fcm/send/fixture'))
 def test_vapid_setup_reuses_key_and_is_private(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);first=public_key(root,create=True)
   self.assertEqual(len(first),87);self.assertEqual(first,public_key(root,create=True))
   self.assertEqual((root/'push-vapid.key').stat().st_mode&0o077,0)

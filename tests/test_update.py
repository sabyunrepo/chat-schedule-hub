import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub.core import Store
from hub.update import run, status, update_lock


class UpdateTests(unittest.TestCase):
    def test_status_does_not_create_missing_databases(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertFalse(status(root)['sources']['kakao']['available'])
            self.assertEqual(list(root.iterdir()), [])

    def test_lock_rejects_concurrent_update_and_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(ValueError, 'failure'):
                with update_lock(root):
                    with self.assertRaisesRegex(RuntimeError, 'already_running'):
                        with update_lock(root):
                            self.fail('concurrent update acquired lock')
                    raise ValueError('failure')
            with update_lock(root):
                pass

    def test_missing_and_unapproved_sources_do_not_create_database(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for source in ('kakao', '../other'):
                with self.assertRaises(ValueError):
                    run('materialize', [source], root)
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_materialization_is_repeatable_without_collection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            Store(root / 'kakao-live.sqlite').db.close()
            for _ in range(2):
                result = run('materialize', ['kakao'], root)
                self.assertEqual(result['sources']['kakao']['applied'], 0)
                self.assertFalse(result['collectionPerformed'])

    def test_sync_requires_transient_token_before_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            Store(root / 'discord-live.sqlite').db.close()
            (root / 'update.json').write_text('{"siteOrigin":"https://example.com"}')
            key = root / 'site-sync.key'
            key.write_text('synthetic-key')
            key.chmod(0o600)
            with patch('hub.update.deliver') as delivery:
                with self.assertRaisesRegex(ValueError, 'site_access_token_required'):
                    run('sync', ['discord'], root)
                delivery.assert_not_called()


if __name__ == '__main__':
    unittest.main()

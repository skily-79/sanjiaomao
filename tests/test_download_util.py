import unittest
from unittest import mock

from ballontranslator.utils import download_util, shared


class CheckLocalFileCacheTest(unittest.TestCase):

    def setUp(self):
        self._old_check_hash = shared.check_local_file_hash
        self._old_cache_data = shared.cache_data
        self._old_cache_updated = shared.CACHE_UPDATED

    def tearDown(self):
        shared.check_local_file_hash = self._old_check_hash
        shared.cache_data = self._old_cache_data
        shared.CACHE_UPDATED = self._old_cache_updated

    def test_loads_cache_before_hash_lookup(self):
        path = r'C:\models\weights.bin'
        expected_hash = 'abc123'
        shared.check_local_file_hash = True
        shared.cache_data = None
        shared.CACHE_UPDATED = False

        def _load_cache():
            shared.cache_data = {path: expected_hash}

        with mock.patch.object(shared, 'load_cache', side_effect=_load_cache) as load_cache, \
                mock.patch('os.path.exists', return_value=True), \
                mock.patch.object(download_util, 'calculate_sha256') as calculate_sha256:
            exists, valid, calculated = download_util.check_local_file(
                path,
                sha256_precal=expected_hash,
                cache_hash=True,
            )

        load_cache.assert_called_once()
        calculate_sha256.assert_not_called()
        self.assertTrue(exists)
        self.assertTrue(valid)
        self.assertEqual(calculated, expected_hash)

    def test_computes_hash_when_cache_misses(self):
        path = r'C:\models\weights.bin'
        expected_hash = 'abc123'
        shared.check_local_file_hash = True
        shared.cache_data = {}
        shared.CACHE_UPDATED = False

        with mock.patch('os.path.exists', return_value=True), \
                mock.patch.object(
                    download_util,
                    'calculate_sha256',
                    return_value='ABC123',
                ) as calculate_sha256:
            exists, valid, calculated = download_util.check_local_file(
                path,
                sha256_precal=expected_hash,
                cache_hash=True,
            )

        calculate_sha256.assert_called_once_with(path)
        self.assertTrue(exists)
        self.assertTrue(valid)
        self.assertEqual(calculated, 'abc123')
        self.assertEqual(shared.cache_data[path], 'abc123')
        self.assertTrue(shared.CACHE_UPDATED)


if __name__ == '__main__':
    unittest.main()

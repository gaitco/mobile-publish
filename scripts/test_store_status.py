import unittest

from store_status import normalize, transfer


class StoreStatusTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(identities={'play': 'com.test.app'}, version='1.2.0',
                            build='42', track='internal')
        self.evidence = dict(app='com.test.app', version='1.2.0', build='42',
                             platform='android', track='internal', state='absent',
                             complete=True, publish_authorized=True, version_available=True)

    def test_wrong_app_track_build_and_readonly_role_block(self):
        for changes in [dict(app='com.other'), dict(track='production'), dict(build='43'),
                        dict(platform='ios'), dict(publish_authorized=False)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(dict(self.evidence, **changes), self.request, 'play')

    def test_partial_history_and_duplicate_build_cannot_claim_unused(self):
        for changes in [dict(complete=False), dict(version_available=False)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(dict(self.evidence, **changes), self.request, 'play')

    def test_query_before_retry_and_never_reupload_accepted(self):
        calls = []
        states = iter(['absent', 'accepted'])
        state = transfer(lambda: next(states), lambda: calls.append('upload') or 'transient')
        self.assertEqual(state, 'accepted')
        self.assertEqual(calls, ['upload'])

    def test_transient_retry_is_bounded_and_unknown_never_retries(self):
        calls = []
        self.assertEqual(transfer(lambda: 'absent', lambda: calls.append(1) or 'transient'), 'unknown')
        self.assertEqual(len(calls), 2)
        calls.clear()
        self.assertEqual(transfer(lambda: 'unknown', lambda: calls.append(1)), 'unknown')
        self.assertEqual(calls, [])

    def test_processing_and_rejected_never_mean_success(self):
        for state in ['processing', 'rejected']:
            self.assertEqual(transfer(lambda: state, lambda: self.fail('duplicate upload')), state)


if __name__ == '__main__':
    unittest.main()

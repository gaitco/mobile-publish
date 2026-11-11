from datetime import datetime, timedelta, timezone
import unittest

try:
    from shorebird_usage import usage_warning
except ImportError:
    usage_warning = None


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)

    def metrics(self, users):
        return {'as_of': self.now.isoformat(), 'granularity': None,
                'current': {'unique_users': users, 'range': {
                    'start': (self.now - timedelta(days=28)).isoformat(),
                    'end': self.now.isoformat()}, 'time_series': None, 'breakdown': None},
                'previous': None}

    def evaluate(self, users, quota=None, threshold=400):
        self.assertIsNotNone(usage_warning, 'usage guard is not implemented')
        if quota is None:
            quota = {'position': dict(installs=0, included_installs=5000,
                                     remaining_installs=5000, at_ceiling=False, consuming_overage=False)}
        return usage_warning(self.metrics(users), quota, threshold, now=self.now)

    def test_warning_only_above_the_configured_user_boundary(self):
        for users in [0, 399, 400]:
            self.assertEqual(self.evaluate(users), '')
        message = self.evaluate(401)
        self.assertIn('401', message)
        self.assertIn('400', message)
        self.assertIn('patch', message)

    def test_threshold_is_project_specific(self):
        self.assertEqual(self.evaluate(401, threshold=500), '')
        self.assertIn('401', self.evaluate(401, threshold=100))

    def test_uses_distinct_window_total_not_daily_sums(self):
        data = self.metrics(350)
        data['current']['time_series'] = [{'unique_users': 300}, {'unique_users': 300}]
        self.assertIsNotNone(usage_warning)
        self.assertEqual(self.evaluate(data['current']['unique_users']), '')

    def test_shared_quota_near_included_allowance_and_unknown_quota_pause(self):
        quota = {'position': dict(installs=4500, included_installs=5000,
                                 remaining_installs=500, at_ceiling=False, consuming_overage=False)}
        self.assertTrue(self.evaluate(20, quota))
        self.assertTrue(usage_warning(self.metrics(20), None, 400, now=self.now))

    def test_missing_malformed_or_stale_metrics_require_a_decision_not_zero_users(self):
        self.assertIsNotNone(usage_warning)
        stale = self.metrics(20)
        stale['as_of'] = (self.now - timedelta(hours=3)).isoformat()
        for data in [None, {}, self.metrics(-1), self.metrics(True), self.metrics('0'), stale]:
            with self.subTest(data=data):
                self.assertTrue(usage_warning(data, None, 400, now=self.now))

    def test_actual_quota_is_reported_without_inventing_a_per_user_fee(self):
        quota = {'position': {'included_installs': 5000, 'installs': 1200,
                             'remaining_installs': 3800, 'at_ceiling': False,
                             'consuming_overage': False}}
        message = self.evaluate(450, quota)
        self.assertIn('1200', message)
        self.assertIn('5000', message)
        self.assertIn('3800', message)

    def test_account_quota_ceiling_or_overage_warns_even_for_a_small_app(self):
        for flag in ['at_ceiling', 'consuming_overage']:
            quota = {'position': {flag: True}}
            self.assertTrue(self.evaluate(20, quota))

    def test_unlimited_stop_ceiling_still_reports_known_usage(self):
        quota = {'position': {'installs': 1200, 'included_installs': 5000,
                             'remaining_installs': None, 'install_ceiling': None,
                             'at_ceiling': False, 'consuming_overage': False}}
        message = self.evaluate(450, quota)
        self.assertIn('1200', message)
        self.assertIn('5000', message)
        self.assertIn('لا يوجد حد إيقاف', message)


if __name__ == '__main__':
    unittest.main()

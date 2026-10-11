from datetime import datetime, timezone, date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


spec = importlib.util.spec_from_file_location("stats", Path(__file__).resolve().parents[1] / "scripts" / "update_stats.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)
NOW = datetime(2026, 10, 11, 20, 45, tzinfo=timezone.utc)


class FixtureClient:
    def __init__(self, private=62, login="devmxlx"):
        self.private = private
        self.login = login
        self.queries = []
        self.payload = None

    def owned_commit_counts(self, username):
        return 65, self.private

    def owned_languages(self, username):
        return [{"name":"TypeScript", "bytes":9000}, {"name":"Python", "bytes":1000}]

    def request(self, path, payload=None):
        if path == "/user":
            return {"login": self.login, "created_at":"2026-01-01T00:00:00Z"}
        self.payload = payload
        return {"data": {"user": {"contributionsCollection": {"contributionCalendar": {
            "totalContributions": 90,
            "privateRepositoryName": "never-publish-this",
            "weeks": [{"contributionDays": [
                {"date": "2025-12-31", "contributionCount": 2, "contributionLevel": "FIRST_QUARTILE"},
                {"date": "2026-01-01", "contributionCount": 3, "contributionLevel": "FIRST_QUARTILE"},
                {"date": "2026-01-02", "contributionCount": 5, "contributionLevel": "FOURTH_QUARTILE"},
            ]}],
        }}}}}


class StatsTests(unittest.TestCase):
    def test_aggregate_only_and_year_filter(self):
        data = stats.collect(FixtureClient(), "devmxlx", NOW)
        self.assertEqual(data["contributions"], 8)
        self.assertEqual(data["commits"], 65)
        self.assertEqual(data["private_commits"], 62)
        self.assertEqual(set(data), stats.PUBLISHED_FIELDS)
        self.assertNotIn("never-publish-this", json.dumps(data))

    def test_no_silent_public_only_fallback(self):
        with self.assertRaisesRegex(ValueError, "No private commits"):
            stats.collect(FixtureClient(private=0), "devmxlx", NOW)

    def test_wrong_account_rejected(self):
        with self.assertRaisesRegex(ValueError, "profile owner"):
            stats.collect(FixtureClient(login="other-user"), "devmxlx", NOW)

    def test_owned_count_filters_author_owner_and_forks(self):
        class Client(stats.GitHub):
            def paged(self, path):
                if path.startswith('/user/repos'):
                    return iter([
                        {"owner":{"login":"devmxlx"},"full_name":"devmxlx/private-fixture","fork":False,"private":True},
                        {"owner":{"login":"devmxlx"},"full_name":"devmxlx/public-fixture","fork":False,"private":False},
                        {"owner":{"login":"devmxlx"},"full_name":"devmxlx/fork","fork":True,"private":True},
                        {"owner":{"login":"other-user"},"full_name":"other-user/repo","fork":False,"private":True},
                    ])
                own = 62 if 'private-fixture' in path else 3
                return iter([{"login":"devmxlx","contributions":own}, {"login":"other-user","contributions":1000}])
        self.assertEqual(Client("fixture").owned_commit_counts("devmxlx"), (65, 62))

    def test_pagination_collects_second_page_and_empty_response(self):
        class Client(stats.GitHub):
            def request(self, path, payload=None):
                if path.endswith('page=1'):
                    return list(range(100))
                return [100]
        self.assertEqual(list(Client("fixture").paged('/user/repos?affiliation=owner')), list(range(101)))
        class Empty(stats.GitHub):
            def request(self, *args, **kwargs):
                return []
        self.assertEqual(list(Empty("fixture").paged('/repos/fixture/empty/contributors')), [])

    def test_invalid_contributor_count_rejected(self):
        class Client(stats.GitHub):
            def paged(self, path):
                if path.startswith('/user/repos'):
                    return iter([{"owner":{"login":"devmxlx"},"full_name":"devmxlx/fixture","fork":False,"private":True}])
                return iter([{"login":"devmxlx","contributions":-1}])
        with self.assertRaisesRegex(ValueError, 'invalid contributor'):
            Client("fixture").owned_commit_counts("devmxlx")

    def test_public_files_drop_unexpected_fields(self):
        data = stats.collect(FixtureClient(), "devmxlx", NOW)
        data["token"] = "never-publish-this-token"
        data["repository"] = "never-publish-this-repository"
        data["calendar"][0]["private_message"] = "never-publish-this-message"
        data["languages"][0]["private_repository"] = "never-publish-this-language-repo"
        data["streaks"]["private_repository"] = "never-publish-this-streak-repo"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stats.publish(data, root)
            graphics = list((root / "assets").glob('*.svg'))
            self.assertEqual(len(graphics), 3)
            for graphic in graphics:
                ET.parse(graphic)
            svg = ''.join(graphic.read_text() for graphic in graphics)
            public_json = (root / "assets" / "stats.json").read_text()
            self.assertNotIn("never-publish", svg + public_json)
            self.assertEqual(set(json.loads(public_json)), stats.PUBLISHED_FIELDS)

    def test_private_languages_are_summed_without_forks_or_other_owners(self):
        class Client(stats.GitHub):
            def paged(self, path):
                return iter([
                    {"owner":{"login":"devmxlx"},"full_name":"devmxlx/private-fixture","fork":False},
                    {"owner":{"login":"devmxlx"},"full_name":"devmxlx/public-fixture","fork":False},
                    {"owner":{"login":"devmxlx"},"full_name":"devmxlx/fork","fork":True},
                    {"owner":{"login":"other"},"full_name":"other/repo","fork":False},
                ])
            def request(self, path, payload=None):
                return {"TypeScript":700,"Python":300} if 'private-fixture' in path else {"TypeScript":300,"CSS":0}
        self.assertEqual(Client('fixture').owned_languages('devmxlx'), [{"name":"TypeScript","bytes":1000},{"name":"Python","bytes":300}])

    def test_streak_crosses_year_boundary_and_allows_empty_today(self):
        days = [{"date":d,"count":c} for d,c in [('2025-12-30',1),('2025-12-31',2),('2026-01-01',3),('2026-01-02',0)]]
        streak = stats.calculate_streaks(days,date(2026,1,2),'2024-07-23')
        self.assertEqual((streak['current'],streak['longest'],streak['active_days']), (3,3,3))
        self.assertEqual(streak['current_start'],'2025-12-30')
        self.assertEqual(stats.calculate_streaks(days,date(2026,1,3),'2024-07-23')['current'],0)

    def test_missing_days_break_streak_and_future_days_are_ignored(self):
        days = [{"date":d,"count":1} for d in ['2026-01-01','2026-01-03','2026-01-04','2026-01-06']]
        streak = stats.calculate_streaks(days,date(2026,1,4),'2026-01-01')
        self.assertEqual((streak['current'],streak['longest'],streak['active_days']), (2,2,3))
        self.assertEqual(streak['longest_start'],'2026-01-03')

    def test_empty_streak_and_language_cards_are_valid(self):
        data = stats.collect(FixtureClient(), 'devmxlx', NOW)
        data['streaks'] = stats.calculate_streaks([],NOW.date(),'2026-01-01')
        data['languages'] = []
        self.assertEqual(data['streaks']['current'],0)
        self.assertEqual(data['streaks']['longest'],0)
        ET.fromstring(stats.render_streaks(data))
        ET.fromstring(stats.render_languages(data))

    def test_new_year_boundary_is_not_a_future_query(self):
        client = FixtureClient()
        now = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
        data = stats.collect(client, "devmxlx", now)
        self.assertEqual(data["year"], 2027)
        variables = client.payload["variables"]
        start = datetime.fromisoformat(variables["from"])
        self.assertLess(start, now)

    def test_imported_history_before_account_creation_is_queried(self):
        class HistoricalClient(FixtureClient):
            def request(self, path, payload=None):
                if path == '/graphql':
                    self.queries.append(payload['variables'])
                return super().request(path, payload)
        client = HistoricalClient()
        data = stats.collect(client, 'devmxlx', NOW, '2023-10-12')
        self.assertEqual(len(client.queries), 4)
        self.assertEqual(data['streaks']['since'], '2023-10-12')
        self.assertTrue(all(datetime.fromisoformat(q['to']) <= NOW for q in client.queries))

    def test_future_history_start_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'future'):
            stats.collect(FixtureClient(), 'devmxlx', NOW, '2026-10-12')

    def test_verified_aggregate_floor_covers_cache_delay_and_expires(self):
        baseline = {'commits':20064,'private_commits':20054,
                    'verified_at':'2026-10-11T20:00:00+00:00','expires_at':'2026-10-13T20:00:00+00:00'}
        data = stats.collect(FixtureClient(), 'devmxlx', NOW)
        calendar = json.dumps(data['calendar'])
        stats.apply_verified_commit_floor(data, baseline, NOW)
        self.assertEqual((data['commits'], data['private_commits']), (20064, 20054))
        self.assertEqual(json.dumps(data['calendar']),calendar)
        live = {'commits':22000,'private_commits':21990}
        self.assertEqual(stats.apply_verified_commit_floor(live,baseline,NOW),live)
        stale = {'commits':65,'private_commits':62}
        stats.apply_verified_commit_floor(stale,baseline,datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(stale,{'commits':65,'private_commits':62})

    def test_invalid_verified_baseline_is_rejected(self):
        baseline = {'commits':10,'private_commits':20,
                    'verified_at':'2026-10-11T20:00:00+00:00','expires_at':'2026-10-13T20:00:00+00:00'}
        with self.assertRaisesRegex(ValueError, 'Inconsistent'):
            stats.apply_verified_commit_floor({},baseline,NOW)


if __name__ == "__main__":
    unittest.main()

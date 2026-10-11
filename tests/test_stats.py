from datetime import datetime, timezone
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

    def request(self, path, payload=None):
        if path == "/user":
            return {"login": self.login}
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stats.publish(data, root)
            svg = (root / "assets" / "stats-mxlx.svg").read_text()
            public_json = (root / "assets" / "stats.json").read_text()
            ET.fromstring(svg)
            self.assertNotIn("never-publish", svg + public_json)
            self.assertEqual(set(json.loads(public_json)), stats.PUBLISHED_FIELDS)

    def test_new_year_boundary_is_not_a_future_query(self):
        client = FixtureClient()
        now = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
        data = stats.collect(client, "devmxlx", now)
        self.assertEqual(data["year"], 2027)
        variables = client.payload["variables"]
        start = datetime.fromisoformat(variables["from"])
        self.assertLess(start, now)


if __name__ == "__main__":
    unittest.main()

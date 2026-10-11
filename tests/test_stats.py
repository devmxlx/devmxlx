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

    def commit_count(self, query):
        self.queries.append(query)
        return self.private if "is:private" in query else 65

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

    def test_incomplete_search_rejected(self):
        class Client(stats.GitHub):
            def request(self, *args, **kwargs):
                return {"total_count": 1, "incomplete_results": True}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            Client("test-fixture").commit_count("author:devmxlx")

    def test_public_files_drop_unexpected_fields(self):
        data = stats.collect(FixtureClient(), "devmxlx", NOW)
        data["token"] = "never-publish-this-token"
        data["repository"] = "never-publish-this-repository"
        data["calendar"][0]["private_message"] = "never-publish-this-message"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stats.publish(data, root)
            svg = (root / "assets" / "stats.svg").read_text()
            public_json = (root / "assets" / "stats.json").read_text()
            ET.fromstring(svg)
            self.assertNotIn("never-publish", svg + public_json)
            self.assertEqual(set(json.loads(public_json)), stats.PUBLISHED_FIELDS)

    def test_new_year_boundary_is_not_a_future_query(self):
        client = FixtureClient()
        now = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
        data = stats.collect(client, "devmxlx", now)
        self.assertEqual(data["year"], 2027)
        self.assertIn("author-date:2027-01-01..2027-12-31", client.queries[0])
        variables = client.payload["variables"]
        start = datetime.fromisoformat(variables["from"])
        self.assertLess(start, now)


if __name__ == "__main__":
    unittest.main()

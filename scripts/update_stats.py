#!/usr/bin/env python3
"""Publish only aggregate GitHub statistics; never publish raw API responses."""

from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_FIELDS = {"username", "year", "commits", "private_commits", "contributions", "updated_on", "calendar"}
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


class GitHub:
    def __init__(self, token):
        if not token:
            raise ValueError("STATS_READ_TOKEN is required; the last snapshot will be kept")
        self.token = token

    def request(self, path, payload=None):
        request = Request(
            "https://api.github.com" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "devmxlx-profile-stats",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise ValueError(f"GitHub API returned HTTP {error.code}; check token access and rate limits") from None

    def commit_count(self, query):
        result = self.request("/search/commits?" + urlencode({"q": query, "per_page": 1}))
        if result.get("incomplete_results") is not False:
            raise ValueError("GitHub returned incomplete search results; keeping the previous snapshot")
        count = result.get("total_count")
        if type(count) is not int or count < 0:
            raise ValueError("GitHub returned an invalid commit count")
        return count


def collect(client, username, now):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", username):
        raise ValueError("Invalid GitHub username")
    if client.request("/user").get("login", "").lower() != username.lower():
        raise ValueError("The statistics token must belong to the profile owner")

    year = now.astimezone(ZoneInfo("Europe/Berlin")).year
    query = f"author:{username} author-date:{year}-01-01..{year}-12-31"
    commits = client.commit_count(query)
    private_commits = client.commit_count(query + " is:private")
    if private_commits <= 0:
        raise ValueError("No private commits are visible; check the token's repository access before publishing")
    if private_commits > commits:
        raise ValueError("GitHub search counts changed during retrieval; retry the update")

    response = client.request("/graphql", {
        "query": """query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar {
                totalContributions
                weeks { contributionDays { date contributionCount contributionLevel } }
              }
            }
          }
        }""",
        "variables": {
            "login": username,
            "from": datetime(year, 1, 1, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(timezone.utc).isoformat(),
            "to": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        },
    })
    if response.get("errors"):
        raise ValueError("GitHub could not return the contribution calendar")
    calendar = response["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            if day["date"].startswith(str(year)):
                if type(day["contributionCount"]) is not int or day["contributionCount"] < 0:
                    raise ValueError("Invalid contribution count")
                datetime.strptime(day["date"], "%Y-%m-%d")
                days.append({
                    "date": day["date"],
                    "count": day["contributionCount"],
                    "level": LEVELS[day["contributionLevel"]],
                })
    # Summing displayed days keeps the card and year-filtered graph consistent.
    return {
        "username": username,
        "year": year,
        "commits": commits,
        "private_commits": private_commits,
        "contributions": sum(day["count"] for day in days),
        "updated_on": now.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat(),
        "calendar": days,
    }


def render(data):
    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
    cells = []
    labels = []
    first = datetime.strptime(data["calendar"][0]["date"], "%Y-%m-%d") if data["calendar"] else None
    offset = (first.weekday() + 1) % 7 if first else 0
    previous_month = None
    for index, day in enumerate(data["calendar"]):
        position = index + offset
        column, row = position // 7, position % 7
        x, y = 74 + column * 19, 267 + row * 17
        value = datetime.strptime(day["date"], "%Y-%m-%d")
        if value.month != previous_month:
            labels.append(f'<text x="{x}" y="253">{value.strftime("%b")}</text>')
            previous_month = value.month
        cells.append(
            f'<rect x="{x}" y="{y}" width="14" height="13" rx="3" fill="{colors[day["level"]]}">'
            f'<title>{escape(day["date"])}: {day["count"]} contributions</title></rect>'
        )
    username = escape(data["username"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-labelledby="title desc">
  <title id="title">{username}'s GitHub activity in {data['year']}</title>
  <desc id="desc">{data['commits']:,} authored commits, including {data['private_commits']:,} private commits, and {data['contributions']:,} contributions. Snapshot from {escape(data['updated_on'])}.</desc>
  <rect x="1" y="1" width="1198" height="428" rx="16" fill="#0d1117" stroke="#28363b"/>
  <g font-family="Arial, Helvetica, sans-serif">
    <text x="32" y="45" fill="#a4b9b0" font-size="14" letter-spacing="3">GITHUB / ACTIVITY {data['year']}</text>
    <text x="1020" y="45" fill="#80ed99" font-size="14">PRIVATE INCLUDED</text>
    <rect x="32" y="67" width="553" height="127" rx="10" fill="#10191e" stroke="#28363b"/>
    <rect x="605" y="67" width="563" height="127" rx="10" fill="#10191e" stroke="#28363b"/>
    <text x="55" y="96" fill="#a4b9b0" font-size="17">AUTHORED COMMITS</text>
    <text x="55" y="149" fill="#e6edf3" font-size="49" font-weight="700">{data['commits']:,}</text>
    <text x="55" y="177" fill="#90a4a1" font-size="15">including {data['private_commits']:,} in private repositories</text>
    <text x="628" y="96" fill="#a4b9b0" font-size="17">CONTRIBUTIONS</text>
    <text x="628" y="149" fill="#e6edf3" font-size="49" font-weight="700">{data['contributions']:,}</text>
    <text x="628" y="177" fill="#90a4a1" font-size="15">GitHub contribution calendar · public + private</text>
    <text x="32" y="232" fill="#e6edf3" font-size="16">A year of activity</text>
    <g fill="#90a4a1" font-size="12">{''.join(labels)}
      <text x="32" y="297">Mon</text><text x="32" y="331">Wed</text><text x="32" y="365">Fri</text>
    </g>
    {''.join(cells)}
    <path d="M32 395 H1168" stroke="#28363b"/>
    <text x="32" y="417" fill="#90a4a1" font-size="12">Source: GitHub API · Aggregate values only · Counts may include automated activity</text>
    <text x="981" y="417" fill="#90a4a1" font-size="12">Updated {escape(data['updated_on'])}</text>
  </g>
</svg>'''


def publish(data, root=ROOT):
    # Explicit schema boundary: no unexpected API fields reach public files.
    safe = {key: data[key] for key in sorted(PUBLISHED_FIELDS)}
    safe["calendar"] = [{key: day[key] for key in ("date", "count", "level")} for day in safe["calendar"]]
    (root / "assets").mkdir(exist_ok=True)
    svg = render(safe)
    (root / "assets" / "stats.svg").write_text(svg + "\n", encoding="utf-8")
    (root / "assets" / "stats.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")


def main():
    try:
        user = os.environ.get("STATS_USER", "devmxlx")
        data = collect(GitHub(os.environ.get("STATS_READ_TOKEN")), user, datetime.now(timezone.utc))
        publish(data)
        print(f"Published {data['commits']} commits and {data['contributions']} contributions for {data['year']}.")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Statistics update failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

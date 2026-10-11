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
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_FIELDS = {"username", "year", "commits", "private_commits", "contributions", "updated_on", "calendar", "commits_scope"}
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
                if response.status == 204:
                    return []
                return json.load(response)
        except HTTPError as error:
            raise ValueError(f"GitHub API returned HTTP {error.code}; check token access and rate limits") from None

    def paged(self, path):
        # Build pagination locally rather than forwarding credentials to a Link URL.
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            entries = self.request(path + separator + urlencode({"per_page": 100, "page": page}))
            if not isinstance(entries, list):
                raise ValueError("GitHub returned an invalid paginated response")
            yield from entries
            if len(entries) < 100:
                return
        raise ValueError("GitHub pagination exceeded the supported limit; keeping the previous snapshot")

    def owned_commit_counts(self, username):
        commits = private_commits = 0
        for repo in self.paged("/user/repos?affiliation=owner"):
            if repo["owner"]["login"].lower() != username.lower() or repo["fork"]:
                continue
            # Metadata-read endpoint: no source-code or commit-message access needed.
            path = "/repos/" + quote(repo["full_name"], safe="/") + "/contributors"
            own = 0
            for contributor in self.paged(path):
                if contributor.get("login", "").lower() != username.lower():
                    continue
                count = contributor["contributions"]
                if type(count) is not int or count < 0:
                    raise ValueError("GitHub returned an invalid contributor commit count")
                own += count
            commits += own
            if repo["private"]:
                private_commits += own
        return commits, private_commits


def collect(client, username, now):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", username):
        raise ValueError("Invalid GitHub username")
    if client.request("/user").get("login", "").lower() != username.lower():
        raise ValueError("The statistics token must belong to the profile owner")

    year = now.astimezone(ZoneInfo("Europe/Berlin")).year
    commits, private_commits = client.owned_commit_counts(username)
    if private_commits <= 0:
        raise ValueError("No private commits are visible; check the token's repository access before publishing")
    if private_commits > commits:
        raise ValueError("GitHub returned inconsistent commit counts; keeping the previous snapshot")

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
        "commits_scope": "owned_nonfork_repositories_all_time",
        "contributions": sum(day["count"] for day in days),
        "updated_on": now.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat(),
        "calendar": days,
    }


def brand_mark(x, y, size=36, fill="#aaff5f"):
    # The pixel asterisk used by mxlx.studio, recreated as native SVG geometry.
    rows = [[4], [1, 4, 7], [2, 4, 6], [3, 4, 5], list(range(9)),
            [3, 4, 5], [2, 4, 6], [1, 4, 7], [4]]
    cells = "".join(f'<rect x="{col}" y="{row}" width="1" height="1"/>'
                    for row, columns in enumerate(rows) for col in columns)
    return f'<g transform="translate({x} {y}) scale({size / 9})" fill="{fill}" shape-rendering="crispEdges">{cells}</g>'


def render(data):
    colors = ["#e2e2e2", "#d4edbf", "#abd884", "#76b848", "#aaff5f"]
    cells = []
    labels = []
    first = datetime.strptime(data["calendar"][0]["date"], "%Y-%m-%d") if data["calendar"] else None
    offset = (first.weekday() + 1) % 7 if first else 0
    previous_month = None
    for index, day in enumerate(data["calendar"]):
        position = index + offset
        column, row = position // 7, position % 7
        x, y = 80 + column * 19, 292 + row * 19
        value = datetime.strptime(day["date"], "%Y-%m-%d")
        if value.month != previous_month:
            labels.append(f'<text x="{x}" y="277">{value.strftime("%b")}</text>')
            previous_month = value.month
        cells.append(
            f'<rect x="{x}" y="{y}" width="14" height="14" rx="2" fill="{colors[day["level"]]}">'
            f'<title>{escape(day["date"])}: {day["count"]} contributions</title></rect>'
        )
    username = escape(data["username"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="480" viewBox="0 0 1200 480" role="img" aria-labelledby="title desc">
  <title id="title">{username}'s GitHub activity in {data['year']}</title>
  <desc id="desc">{data['commits']:,} authored commits in owned non-fork repositories, all time, including {data['private_commits']:,} private commits. {data['contributions']:,} contributions in {data['year']}. Snapshot from {escape(data['updated_on'])}.</desc>
  <rect width="1200" height="480" rx="18" fill="#f5f5f5"/>
  <g font-family="Arial, Helvetica, sans-serif" fill="#111111">
    <text x="32" y="43" fill="#777777" font-size="16">/003</text>
    <text x="87" y="43" font-size="22" font-weight="600" letter-spacing="-.7">GitHub activity</text>
    <rect x="952" y="21" width="153" height="32" rx="16" fill="#aaff5f"/>
    <text x="974" y="42" font-size="14" font-weight="600">Private included</text>
    {brand_mark(1133, 21, 32, '#111111')}
    <path d="M32 68 H1168 M595 91 V207" stroke="#d8d8d8"/>
    <text x="32" y="106" fill="#666666" font-size="16">Authored commits · all time</text>
    <text x="29" y="171" font-size="65" font-weight="600" letter-spacing="-3">{data['commits']:,}</text>
    <text x="32" y="202" fill="#666666" font-size="16">{data['private_commits']:,} private · owned repositories</text>
    <text x="627" y="106" fill="#666666" font-size="16">Contributions · {data['year']}</text>
    <text x="624" y="171" font-size="65" font-weight="600" letter-spacing="-3">{data['contributions']:,}</text>
    <text x="627" y="202" fill="#666666" font-size="16">GitHub calendar · public + private</text>
    <path d="M32 227 H1168" stroke="#d8d8d8"/>
    <text x="32" y="253" font-size="16" font-weight="600">A year of activity.</text>
    <g fill="#777777" font-size="13">{''.join(labels)}
      <text x="32" y="323">Mon</text><text x="32" y="361">Wed</text><text x="32" y="399">Fri</text>
    </g>
    {''.join(cells)}
    <path d="M32 439 H1168" stroke="#d8d8d8"/>
    <text x="32" y="463" fill="#777777" font-size="12">GitHub API · Aggregate values only · May include automated activity</text>
    <text x="982" y="463" fill="#777777" font-size="12">Updated {escape(data['updated_on'])}</text>
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

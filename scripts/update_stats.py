#!/usr/bin/env python3
"""Publish only aggregate GitHub statistics; never publish raw API responses."""

from datetime import datetime, timezone, timedelta, date
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
PUBLISHED_FIELDS = {"username", "year", "commits", "private_commits", "contributions", "updated_on", "calendar", "commits_scope", "languages", "streaks", "languages_scope", "languages_updated_on", "languages_file_count", "languages_project_count", "languages_imported_content_included"}
STREAK_FIELDS = {"current", "longest", "active_days", "current_start", "current_end", "longest_start", "longest_end", "since"}
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

    def owned_repositories(self, username):
        for repo in self.paged("/user/repos?affiliation=owner"):
            if repo["owner"]["login"].lower() != username.lower() or repo["fork"]:
                continue
            yield repo

    def owned_commit_counts(self, username):
        commits = private_commits = 0
        for repo in self.owned_repositories(username):
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

    def owned_languages(self, username):
        totals = {}
        for repo in self.owned_repositories(username):
            values = self.request("/repos/" + quote(repo["full_name"], safe="/") + "/languages")
            if not isinstance(values, dict):
                raise ValueError("GitHub returned invalid language statistics")
            for name, byte_count in values.items():
                if not isinstance(name, str) or not name or type(byte_count) is not int or byte_count < 0:
                    raise ValueError("GitHub returned invalid language counts")
                if byte_count:
                    totals[name] = totals.get(name, 0) + byte_count
        return [{"name": name, "bytes": count} for name, count in
                sorted(totals.items(), key=lambda item: (-item[1], item[0]))]


def calculate_streaks(days, today, since):
    """Calendar days with any contribution; today has a grace period until it ends."""
    entries = {}
    for day in days:
        value = date.fromisoformat(day["date"])
        if value > today:
            continue
        if value in entries:
            raise ValueError("GitHub returned duplicate calendar days")
        entries[value] = day["count"]
    runs = []
    active_days = 0
    start = end = None
    for value, count in sorted(entries.items()):
        if not count:
            continue
        active_days += 1
        if end is None or value != end + timedelta(days=1):
            if start is not None:
                runs.append((start, end))
            start = value
        end = value
    if start is not None:
        runs.append((start, end))
    longest = max(runs, key=lambda run: (run[1] - run[0]).days, default=None)
    current = runs[-1] if runs and runs[-1][1] >= today - timedelta(days=1) else None
    def length(run):
        return (run[1] - run[0]).days + 1 if run else 0
    return {
        "current": length(current), "longest": length(longest), "active_days": active_days,
        "current_start": current[0].isoformat() if current else None,
        "current_end": current[1].isoformat() if current else None,
        "longest_start": longest[0].isoformat() if longest else None,
        "longest_end": longest[1].isoformat() if longest else None,
        "since": since,
    }


def collect(client, username, now, history_start=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", username):
        raise ValueError("Invalid GitHub username")
    profile = client.request("/user")
    if profile.get("login", "").lower() != username.lower():
        raise ValueError("The statistics token must belong to the profile owner")

    year = now.astimezone(ZoneInfo("Europe/Berlin")).year
    commits, private_commits = client.owned_commit_counts(username)
    if private_commits <= 0:
        raise ValueError("No private commits are visible; check the token's repository access before publishing")
    if private_commits > commits:
        raise ValueError("GitHub returned inconsistent commit counts; keeping the previous snapshot")

    since = datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Berlin")).date()
    today = now.astimezone(ZoneInfo("Europe/Berlin")).date()
    if since > today:
        raise ValueError("GitHub returned an invalid account creation date")
    if history_start:
        requested = date.fromisoformat(history_start)
        if requested > today:
            raise ValueError("The history start cannot be in the future")
        # Imported Git history can have author dates before account creation.
        since = min(since, requested)
    all_days = []
    for calendar_year in range(since.year, year + 1):
        start = datetime(calendar_year, 1, 1, tzinfo=ZoneInfo("Europe/Berlin"))
        end = min(now, datetime(calendar_year + 1, 1, 1, tzinfo=ZoneInfo("Europe/Berlin")) - timedelta(seconds=1))
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
            "from": start.astimezone(timezone.utc).isoformat(),
            "to": end.astimezone(timezone.utc).isoformat(timespec="seconds"),
        },
        })
        if response.get("errors"):
            raise ValueError("GitHub could not return the contribution calendar")
        calendar = response["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                value = date.fromisoformat(day["date"])
                if value.year != calendar_year or not since <= value <= today:
                    continue
                if type(day["contributionCount"]) is not int or day["contributionCount"] < 0:
                    raise ValueError("Invalid contribution count")
                all_days.append({"date": day["date"], "count": day["contributionCount"],
                                 "level": LEVELS[day["contributionLevel"]]})
    all_days.sort(key=lambda day: day["date"])
    days = [day for day in all_days if day["date"].startswith(str(year))]
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
        "streaks": calculate_streaks(all_days, today, since.isoformat()),
        "languages": client.owned_languages(username),
        "languages_scope": "github_repository_code_bytes",
        "languages_updated_on": today.isoformat(),
        "languages_file_count": None,
        "languages_project_count": None,
        "languages_imported_content_included": None,
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


def card(title, index, description, body, height, updated):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
  <rect width="1200" height="{height}" rx="18" fill="#f5f5f5"/>
  <g font-family="Arial, Helvetica, sans-serif" fill="#111111">
    <text x="32" y="43" fill="#777777" font-size="16">/{index}</text>
    <text x="87" y="43" font-size="22" font-weight="600" letter-spacing="-.7">{escape(title)}</text>
    <rect x="952" y="21" width="153" height="32" rx="16" fill="#aaff5f"/>
    <text x="974" y="42" font-size="14" font-weight="600">Private included</text>
    {brand_mark(1133, 21, 32, '#111111')}
    <path d="M32 68 H1168" stroke="#d8d8d8"/>
    {body}
    <text x="982" y="{height - 17}" fill="#777777" font-size="12">Updated {escape(updated)}</text>
  </g>
</svg>'''


def date_range(start, end):
    if not start:
        return "No active streak"
    def label(value):
        return date.fromisoformat(value).strftime("%d %b %Y").lstrip("0")
    return label(start) if start == end else label(start) + " – " + label(end)


def render_streaks(data):
    streak = data["streaks"]
    body = f'''<rect x="32" y="91" width="351" height="153" rx="16" fill="#aaff5f"/>
      <path d="M411 91 V244 M801 91 V244" stroke="#d8d8d8"/>
      <text x="51" y="121" font-size="16">Current streak · days</text>
      <text x="48" y="195" font-size="72" font-weight="600" letter-spacing="-3">{streak['current']:,}</text>
      <text x="51" y="224" font-size="14">{escape(date_range(streak['current_start'], streak['current_end']))}</text>
      <text x="441" y="121" fill="#666666" font-size="16">Longest streak · days</text>
      <text x="438" y="195" font-size="72" font-weight="600" letter-spacing="-3">{streak['longest']:,}</text>
      <text x="441" y="224" fill="#666666" font-size="14">{escape(date_range(streak['longest_start'], streak['longest_end']))}</text>
      <text x="831" y="121" fill="#666666" font-size="16">Days with contributions</text>
      <text x="828" y="195" font-size="72" font-weight="600" letter-spacing="-3">{streak['active_days']:,}</text>
      <text x="831" y="224" fill="#666666" font-size="14">Public + private · all time</text>
      <path d="M32 265 H1168" stroke="#d8d8d8"/>
      <text x="32" y="289" fill="#777777" font-size="12">Since {escape(streak['since'])} · Any contribution counts · Europe/Berlin · Today has a grace period</text>'''
    description = f"Current streak: {streak['current']} days. Longest streak: {streak['longest']} days. {streak['active_days']} active days since {streak['since']}, including private contributions."
    return card("Contribution streaks", "004", description, body, 306, data["updated_on"])


def render_languages(data):
    entries = data["languages"]
    total = sum(item["bytes"] for item in entries)
    displayed = [dict(item) for item in entries[:6]]
    if len(entries) > 6:
        displayed.append({"name": "Other languages", "bytes": sum(item["bytes"] for item in entries[6:])})
    colors = ["#aaff5f", "#111111", "#575757", "#838383", "#aaaaaa", "#c5c5c5", "#d8d8d8"]
    rows = []
    for i, item in enumerate(displayed):
        percentage = item["bytes"] / total * 100
        y = 131 + i * 54
        percent_text = "&lt;0.1%" if 0 < percentage < 0.1 else f"{percentage:.1f}%"
        rows.append(f'''<rect x="32" y="{y - 13}" width="10" height="10" rx="2" fill="{colors[i]}"/>
          <text x="53" y="{y}" font-size="18" font-weight="600">{escape(item['name'])}</text>
          <text x="1168" y="{y}" font-size="17" text-anchor="end">{percent_text}</text>
          <rect x="32" y="{y + 14}" width="1136" height="7" rx="3.5" fill="#e2e2e2"/>
          <rect x="32" y="{y + 14}" width="{1136 * percentage / 100:.2f}" height="7" rx="3.5" fill="{colors[i]}"/>''')
    if not displayed:
        rows.append('<text x="32" y="139" fill="#666666" font-size="18">No language bytes reported by GitHub yet.</text>')
    height = 165 + max(1, len(displayed)) * 54
    source_snapshot = data.get('languages_scope') == 'accessible_project_source_bytes'
    subtitle = (f"Source-file bytes · {data['languages_file_count']:,} files · {data['languages_project_count']} accessible projects"
                if source_snapshot else "Share of GitHub-detected code bytes · owned non-fork repositories")
    excluded = "Dependencies, build output and duplicates excluded" if data.get('languages_imported_content_included') else "Dependencies, build output, duplicates and imported learning pages excluded"
    footnote = (excluded + " · Aggregate values only"
                if source_snapshot else "Code distribution, not time spent · Aggregate public + private values · No repository names")
    body = f'''<text x="32" y="94" fill="#777777" font-size="14">{escape(subtitle)}</text>
       {''.join(rows)}
       <path d="M32 {height - 41} H1168" stroke="#d8d8d8"/>
       <text x="32" y="{height - 17}" fill="#777777" font-size="12">{escape(footnote)}</text>'''
    description = "; ".join(f"{item['name']}: {item['bytes'] / total * 100:.1f}%" for item in displayed) if total else "No language bytes reported."
    return card("Most-used languages", "005", description, body, height,
                data.get('languages_updated_on',data['updated_on']))


def publish(data, root=ROOT):
    # Explicit schema boundary: no unexpected API fields reach public files.
    safe = {key: data[key] for key in sorted(PUBLISHED_FIELDS)}
    safe["calendar"] = [{key: day[key] for key in ("date", "count", "level")} for day in safe["calendar"]]
    safe["languages"] = [{key:item[key] for key in ("name","bytes","files","code_lines") if key in item}
                         for item in safe["languages"]]
    safe["streaks"] = {key: safe["streaks"][key] for key in sorted(STREAK_FIELDS)}
    (root / "assets").mkdir(exist_ok=True)
    # Render everything before writing so API/schema/render errors keep the previous snapshot.
    graphics = {"stats-mxlx.svg": render(safe), "streaks-mxlx.svg": render_streaks(safe),
                "languages-mxlx.svg": render_languages(safe)}
    for name, svg in graphics.items():
        (root / "assets" / name).write_text(svg + "\n", encoding="utf-8")
    (root / "assets" / "stats.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")


def apply_verified_commit_floor(data, baseline, now):
    """Temporary aggregate lower bound for GitHub's delayed contributor cache."""
    verified = datetime.fromisoformat(baseline["verified_at"])
    expires = datetime.fromisoformat(baseline["expires_at"])
    if verified.tzinfo is None or expires.tzinfo is None or not verified < expires:
        raise ValueError("Invalid verified aggregate baseline dates")
    if expires - verified > timedelta(days=2):
        raise ValueError("Verified aggregate baseline may last at most two days")
    for key in ("commits", "private_commits"):
        if type(baseline[key]) is not int or baseline[key] < 0:
            raise ValueError("Invalid verified aggregate baseline counts")
    if baseline["private_commits"] > baseline["commits"]:
        raise ValueError("Inconsistent verified aggregate baseline")
    if verified <= now < expires:
        data["commits"] = max(data["commits"], baseline["commits"])
        data["private_commits"] = max(data["private_commits"], baseline["private_commits"])
        data["commits"] = max(data["commits"], data["private_commits"])
    return data


def apply_source_language_snapshot(data, snapshot, now):
    """Keep a locally measured source snapshot independent of the cloud refresh date."""
    scanned = datetime.fromisoformat(snapshot['scanned_at'])
    if scanned.tzinfo is None or scanned > now:
        raise ValueError('Invalid source scan timestamp')
    if snapshot.get('metric') != 'source_file_bytes' or type(snapshot.get('imported_content_included')) is not bool:
        raise ValueError('Unexpected source scan methodology')
    if any(type(snapshot[k]) is not int or snapshot[k] <= 0 for k in ('file_count','project_count')):
        raise ValueError('Invalid source scan coverage')
    entries = []
    seen = set()
    for item in snapshot['languages']:
        name = item['name']
        if not isinstance(name,str) or not name or name in seen or len(name)>80:
            raise ValueError('Invalid source scan language')
        if any(type(item[k]) is not int or item[k] < 0 for k in ('bytes','files','code_lines')):
            raise ValueError('Invalid source scan language counts')
        seen.add(name)
        entries.append({k:item[k] for k in ('name','bytes','files','code_lines')})
    if sum(item['files'] for item in entries) != snapshot['file_count']:
        raise ValueError('Source scan file total does not match')
    data['languages'] = sorted(entries,key=lambda item:(-item['bytes'],item['name']))
    data['languages_scope'] = 'accessible_project_source_bytes'
    data['languages_updated_on'] = scanned.astimezone(ZoneInfo('Europe/Berlin')).date().isoformat()
    data['languages_file_count'] = snapshot['file_count']
    data['languages_project_count'] = snapshot['project_count']
    data['languages_imported_content_included'] = snapshot['imported_content_included']
    return data


def main():
    try:
        user = os.environ.get("STATS_USER", "devmxlx")
        data = collect(GitHub(os.environ.get("STATS_READ_TOKEN")), user,
                       datetime.now(timezone.utc), os.environ.get("STATS_HISTORY_START"))
        baseline_path = ROOT / "stats-cache-baseline.json"
        if baseline_path.exists():
            data = apply_verified_commit_floor(data, json.loads(baseline_path.read_text()),
                                               datetime.now(timezone.utc))
        source_path = ROOT / 'assets' / 'language-source-snapshot.json'
        if source_path.exists():
            data = apply_source_language_snapshot(data,json.loads(source_path.read_text()),
                                                   datetime.now(timezone.utc))
        publish(data)
        print(f"Published {data['commits']} all-time owned-repository commits and {data['contributions']} contributions for {data['year']}.")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Statistics update failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

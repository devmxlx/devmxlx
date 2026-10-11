# Profile statistics

The SVG is generated from real GitHub API data. Only aggregate counts and contribution-calendar dates/counts are written to `assets/stats.json` and `assets/stats.svg`. Neither private repository names nor credentials are published.

## Automatic refresh

1. Create a separate fine-grained GitHub token for the repositories to include. Start with the mandatory **Metadata: read** permission only: GitHub documents commit search as requiring no additional fine-grained permissions. The runtime verifies that private commits are visible before publishing an update. If GitHub refuses private commit search for this token, inspect the returned permission requirements before granting anything broader.
2. Store it as the Actions secret **STATS_READ_TOKEN** in this profile repository. Do not put it in a file, README, image URL or commit.
3. Set the Actions repository variable **PRIVATE_STATS_ENABLED** to **true**.
4. Run **Actions → Update private-inclusive profile stats → Run workflow**.

The workflow refreshes at **11:07, 15:07, 19:07 and 23:07, Europe/Berlin**. These times follow the separate activity workflow. GitHub schedules and search indexing can be delayed. An expiring token must be renewed before its expiry; a missing, expired or insufficient token makes the job fail while preserving the last published snapshot.

The built-in `GITHUB_TOKEN` pushes the resulting files and is scoped to this profile repository. The read-only token is used only for GitHub API reads. No external statistics service receives it.

## Counting rules

- Commits: GitHub search `author:USERNAME author-date:YYYY-01-01..YYYY-12-31`. GitHub indexes commits on default branches. Search reflects repositories accessible to the token and may lag newly pushed commits. Incomplete search results are rejected.
- Private commits: the same query with `is:private`.
- Contributions: GitHub's contribution calendar from the start of the current year to the current time. The profile's private-contribution visibility setting controls anonymized private activity in this calendar.
- The two counts measure different things and are not added together.

The updater uses Python's standard library, validates the token's account, and writes an explicit allowlist of fields. It never writes raw search results, API tokens, repository lists, commit details or GraphQL response bodies.

## Sources

- [GitHub commit search and fine-grained token permissions](https://docs.github.com/en/rest/search/search#search-commits)
- [GitHub contribution calendar](https://docs.github.com/en/graphql/reference/users#contributioncalendar)
- [GitHub contribution criteria](https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference)

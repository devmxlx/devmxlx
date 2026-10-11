# Profile statistics

The SVG is generated from real GitHub API data. Only aggregate counts and contribution-calendar dates/counts are written to `assets/stats.json` and `assets/stats.svg`. Neither private repository names nor credentials are published.

## Automatic refresh

1. Create a separate fine-grained GitHub token for the repositories to include, with **Metadata: read** only. The updater uses repository contributor counts, which work with this permission for private repositories. Contents, administration, workflow and account permissions are unnecessary.
2. Store it as the Actions secret **STATS_READ_TOKEN** in this profile repository. Do not put it in a file, README, image URL or commit.
3. Set the Actions repository variable **PRIVATE_STATS_ENABLED** to **true**.
4. Run **Actions → Update private-inclusive profile stats → Run workflow**.

The workflow refreshes at **11:07, 15:07, 19:07 and 23:07, Europe/Berlin**. These times follow the separate activity workflow. GitHub schedules and search indexing can be delayed. An expiring token must be renewed before its expiry; a missing, expired or insufficient token makes the job fail while preserving the last published snapshot.

The built-in `GITHUB_TOKEN` pushes the resulting files and is scoped to this profile repository. The read-only token is used only for GitHub API reads. No external statistics service receives it.

## Counting rules

- Commits: sum the profile owner's `contributions` count from `GET /repos/{owner}/{repo}/contributors`, for owned non-fork repositories returned by the token. This is an all-time repository contributor counter, not a calendar-year search count. Repositories owned by other accounts and forks are excluded.
- Private commits: the subset of those counts from repositories with `private: true`.
- GitHub caches contributor counts for a few hours. Its attribution groups associated author emails by GitHub account; the API links only the first 500 distinct author emails in each repository. Large multi-author repositories can therefore have attribution limits.
- Contributions: GitHub's contribution calendar from the start of the current year to the current time. The profile's private-contribution visibility setting controls anonymized private activity in this calendar.
- The two counts measure different things and are not added together.

The updater uses Python's standard library, validates the token's account, handles repository/contributor pagination and empty repositories, and writes an explicit allowlist of fields. It never writes API tokens, repository lists, contributor identities, commit details or GraphQL response bodies. API failures preserve the previous snapshot.

## Credential access

The separate token has metadata-read access to current and future repositories owned by the account, expires on **2027-10-11**, and is stored as the encrypted Actions secret `STATS_READ_TOKEN`. It can read repository metadata and aggregate contributor statistics; it has no permission to read private source files, push code, modify repositories or change account settings. Anyone who obtains it could read the metadata it permits, so restrict workflow edits and do not paste it into public files or logs. The token can be revoked in GitHub's fine-grained token settings.

## Sources

- [GitHub repository contributor counts and metadata permissions](https://docs.github.com/en/rest/repos/repos#list-repository-contributors)
- [GitHub contribution calendar](https://docs.github.com/en/graphql/reference/users#contributioncalendar)
- [GitHub contribution criteria](https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference)

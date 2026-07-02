from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from requests import Session
from tqdm import tqdm

API_URL = "https://api.github.com"
DEFAULT_ORG = "MiSTer-devel"
REPORT_PREFIX = "mister_sys_folders_"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "mister_sys_check.json"

CSV_HEADER = [
    "Core Name",
    "Sys Date",
    "Sys Time",
    "User",
    "Latest RBF Date",
    "Release Newer Than SYS?",
    "Status",
]


@dataclass(frozen=True)
class ReportRow:
    core_name: str
    sys_datetime: datetime
    user: str
    latest_rbf_datetime: datetime | None
    release_newer: bool
    status: str

    def as_csv_row(self) -> list[str]:
        return [
            self.core_name,
            self.sys_datetime.strftime("%d/%m/%Y"),
            self.sys_datetime.strftime("%H:%M:%S"),
            self.user,
            self.latest_rbf_datetime.strftime("%d/%m/%Y")
            if self.latest_rbf_datetime
            else "",
            "Yes" if self.release_newer else "No",
            self.status,
        ]


@dataclass
class RunSummary:
    total_repos: int = 0
    checked_repos: int = 0
    repos_with_sys: int = 0
    errors_encountered: int = 0
    skipped_archived: list[str] | None = None

    def __post_init__(self) -> None:
        if self.skipped_archived is None:
            self.skipped_archived = []


@dataclass(frozen=True)
class RateLimitStatus:
    remaining: int
    reset_time: datetime


@dataclass(frozen=True)
class AppConfig:
    excluded_repos: frozenset[str]
    special_sys_paths: dict[str, str]


def load_config(path: Path) -> AppConfig:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config file is not valid JSON: {path}") from exc

    excluded_repos = data.get("excluded_repos", [])
    special_sys_paths = data.get("special_sys_paths", {})

    if not isinstance(excluded_repos, list) or not all(
        isinstance(repo, str) for repo in excluded_repos
    ):
        raise ValueError("Config field 'excluded_repos' must be a list of strings.")

    if not isinstance(special_sys_paths, dict) or not all(
        isinstance(repo, str) and isinstance(path_value, str)
        for repo, path_value in special_sys_paths.items()
    ):
        raise ValueError(
            "Config field 'special_sys_paths' must be an object of string values."
        )

    return AppConfig(
        excluded_repos=frozenset(excluded_repos),
        special_sys_paths=dict(special_sys_paths),
    )


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        logging.error("Could not parse GitHub datetime: %s", value)
        return None


def create_session(token: str | None = None) -> Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "mister-sys-check",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def github_get(session: Session, url: str, **params: Any) -> Any:
    response = session.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def get_rate_limit_status(session: Session) -> RateLimitStatus | None:
    try:
        data = github_get(session, f"{API_URL}/rate_limit")
    except requests.RequestException as exc:
        logging.error("Rate limit check failed: %s", exc)
        return None

    core = data["resources"]["core"]
    reset_time = datetime.fromtimestamp(core["reset"], tz=timezone.utc)
    return RateLimitStatus(remaining=core["remaining"], reset_time=reset_time)


def get_repos(session: Session, org: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1

    while True:
        try:
            data = github_get(
                session,
                f"{API_URL}/orgs/{org}/repos",
                type="all",
                per_page=100,
                page=page,
            )
        except requests.RequestException as exc:
            logging.error("Repo list failed: %s", exc)
            break

        if not data:
            break

        repos.extend(data)
        page += 1

    return repos


def get_latest_commit(session: Session, org: str, repo_name: str, path: str) -> dict[str, Any] | None:
    try:
        data = github_get(
            session,
            f"{API_URL}/repos/{org}/{repo_name}/commits",
            path=path,
            per_page=1,
        )
    except requests.RequestException as exc:
        logging.error("Commit request failed for %s:%s: %s", repo_name, path, exc)
        return None

    return data[0] if data else None


def commit_author(commit: dict[str, Any]) -> str:
    github_author = commit.get("author") or {}
    if github_author.get("login"):
        return github_author["login"]

    author = commit.get("commit", {}).get("author", {})
    return author.get("name") or "Unknown"


def build_report(
    session: Session,
    repos: Iterable[dict[str, Any]],
    org: str,
    config: AppConfig,
    exclude_archived: bool,
) -> tuple[list[ReportRow], RunSummary]:
    summary = RunSummary()
    results: list[ReportRow] = []

    for repo in tqdm(list(repos), desc="Checking repositories"):
        repo_name = repo["name"]
        summary.total_repos += 1

        if repo_name in config.excluded_repos:
            continue

        is_archived = repo.get("archived", False)
        if exclude_archived and is_archived:
            summary.skipped_archived.append(repo_name)
            continue

        summary.checked_repos += 1
        status = "Deprecated" if is_archived else "Active"
        sys_path = config.special_sys_paths.get(repo_name, "sys")
        sys_commit = get_latest_commit(session, org, repo_name, sys_path)

        if not sys_commit:
            summary.errors_encountered += 1
            continue

        sys_datetime = parse_github_datetime(
            sys_commit.get("commit", {}).get("committer", {}).get("date")
        )
        if not sys_datetime:
            summary.errors_encountered += 1
            continue

        rbf_commit = get_latest_commit(session, org, repo_name, "releases")
        rbf_datetime = parse_github_datetime(
            (rbf_commit or {}).get("commit", {}).get("committer", {}).get("date")
        )

        summary.repos_with_sys += 1
        results.append(
            ReportRow(
                core_name=repo_name,
                sys_datetime=sys_datetime,
                user=commit_author(sys_commit),
                latest_rbf_datetime=rbf_datetime,
                release_newer=bool(rbf_datetime and rbf_datetime >= sys_datetime),
                status=status,
            )
        )

    results.sort(key=lambda row: row.sys_datetime)
    return results, summary


def estimate_commit_requests(
    repos: Iterable[dict[str, Any]],
    config: AppConfig,
    exclude_archived: bool,
) -> int:
    checked_repos = 0
    for repo in repos:
        repo_name = repo["name"]
        if repo_name in config.excluded_repos:
            continue
        if exclude_archived and repo.get("archived", False):
            continue
        checked_repos += 1

    # Most checked repos need a sys lookup, and repos with sys need a release lookup.
    # Use the upper bound so we fail early instead of writing partial reports.
    return checked_repos * 2


def archive_existing_reports(reports_dir: Path, archive_dir: Path) -> list[Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived: list[Path] = []
    for report in reports_dir.glob(f"{REPORT_PREFIX}*.csv"):
        destination = archive_dir / report.name
        if destination.exists():
            destination = archive_dir / f"{report.stem}_{int(time.time())}{report.suffix}"
        shutil.move(str(report), destination)
        archived.append(destination)

    return archived


def write_csv(rows: Iterable[ReportRow], reports_dir: Path, archive_old: bool = True) -> Path:
    archive_dir = reports_dir / "archive"
    if archive_old:
        archive_existing_reports(reports_dir, archive_dir)
    else:
        reports_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = reports_dir / f"{REPORT_PREFIX}{timestamp}.csv"

    with report_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_HEADER)
        writer.writerows(row.as_csv_row() for row in rows)

    return report_path


def print_report(rows: list[ReportRow], summary: RunSummary, report_path: Path, elapsed: float) -> None:
    print("\nRepositories with 'sys' folder:")
    for row in rows:
        rbf_date = (
            row.latest_rbf_datetime.strftime("%d/%m/%Y")
            if row.latest_rbf_datetime
            else ""
        )
        print(
            f"{row.core_name} - Sys: {row.sys_datetime:%d/%m/%Y %H:%M:%S} "
            f"by {row.user} - RBF: {rbf_date} - "
            f"Release newer? {'Yes' if row.release_newer else 'No'} - Status: {row.status}"
        )

    no_new_release_cores = [row.core_name for row in rows if not row.release_newer]
    print("\nCores where no new release since .sys was updated:")
    print(len(no_new_release_cores))
    for core in no_new_release_cores:
        print(core)

    if summary.skipped_archived:
        print("\nArchived/Deprecated cores skipped:")
        print(len(summary.skipped_archived))
        for core in summary.skipped_archived:
            print(core)

    print(f"\nCSV saved as: {report_path}")
    print("\nSummary:")
    print(f"Total repositories retrieved: {summary.total_repos}")
    print(f"Repositories checked: {summary.checked_repos}")
    print(f"Repositories with a 'sys' folder: {summary.repos_with_sys}")
    print(f"Errors encountered: {summary.errors_encountered}")

    minutes, seconds = divmod(int(elapsed), 60)
    print(f"\nTotal runtime: {minutes} minutes, {seconds} seconds")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check when .sys folders were last updated in MiSTer cores."
    )
    parser.add_argument("--org", default=DEFAULT_ORG, help="GitHub organization to scan.")
    parser.add_argument(
        "--reports-dir",
        default=PROJECT_ROOT / "reports",
        type=Path,
        help="Directory where the latest CSV report is written.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        type=Path,
        help="JSON config file with excluded repos and special .sys paths.",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived GitHub repositories in the report.",
    )
    parser.add_argument(
        "--keep-old-reports",
        action="store_true",
        help="Do not move existing reports into reports/archive before writing a new one.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub token. Defaults to the GITHUB_TOKEN environment variable.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed request errors.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    start_time = time.time()
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    session = create_session(args.token)

    rate_limit = get_rate_limit_status(session)
    if rate_limit:
        print(f"Remaining GitHub requests: {rate_limit.remaining}")
        print(f"Rate limit resets: {rate_limit.reset_time.astimezone():%Y-%m-%d %H:%M:%S %Z}")

    print(f"Fetching repositories from {args.org}...")
    repos = get_repos(session, args.org)
    if not repos:
        print("No repositories found; no report was written.", file=sys.stderr)
        return 1

    required_requests = estimate_commit_requests(
        repos,
        config=config,
        exclude_archived=not args.include_archived,
    )
    rate_limit = get_rate_limit_status(session)
    if rate_limit and rate_limit.remaining < required_requests:
        print(
            "\nNot enough GitHub API quota remains to create a complete report.",
            file=sys.stderr,
        )
        print(
            f"Need up to {required_requests} more requests, but only "
            f"{rate_limit.remaining} remain until "
            f"{rate_limit.reset_time.astimezone():%Y-%m-%d %H:%M:%S %Z}.",
            file=sys.stderr,
        )
        print(
            "Set GITHUB_TOKEN to use an authenticated GitHub API limit, then run again.",
            file=sys.stderr,
        )
        return 1

    rows, summary = build_report(
        session=session,
        repos=repos,
        org=args.org,
        config=config,
        exclude_archived=not args.include_archived,
    )
    report_path = write_csv(
        rows,
        reports_dir=args.reports_dir,
        archive_old=not args.keep_old_reports,
    )
    print_report(rows, summary, report_path, time.time() - start_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

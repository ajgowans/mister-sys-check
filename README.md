# MiSTer Sys Check

Checks MiSTer cores for the latest commit touching their `.sys` folder and compares it with the latest commit in `releases`.

## One-click run

Double-click `run_mister_sys_check.command` on macOS. The first run creates a local `.venv` and installs the small set of dependencies.

Reports are written to `reports/`. When a new report is created, older `mister_sys_folders_*.csv` files in `reports/` are moved to `reports/archive/`.

## Terminal run

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python mistersyscheck.py
```

## GitHub rate limits

Unauthenticated GitHub API requests are rate limited. To raise the limit, set a token before running:

```sh
export GITHUB_TOKEN="your-token"
python mistersyscheck.py
```

The token is read from the environment and is not stored in the project.

## Useful options

```sh
python mistersyscheck.py --include-archived
python mistersyscheck.py --keep-old-reports
python mistersyscheck.py --reports-dir /path/to/reports
```

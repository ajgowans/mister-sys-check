# mister-sys-check
A script that checks all the user facing MiSTer FPGA core repos and checks when .sys files were last updated 

# MiSTer `sys/` Folder Checker

This Python script audits repositories within the [`MiSTer-devel`](https://github.com/MiSTer-devel) GitHub organization to determine which cores have an active `sys/` folder and when it was last updated. The output includes contributor info and repository status (active or deprecated), and results are saved to a timestamped CSV file.

## Features

- Automatically installs missing dependencies (`tqdm` and `requests`)
- Queries GitHub API for all repositories in `MiSTer-devel`
- Skips a configurable list of non-core or utility repositories
- Checks each repository for a `sys/` folder
- Extracts the date and author of the last commit to that folder
- Exports results to a timestamped CSV
- Provides a clear terminal summary with a progress bar and spinner animations

## Requirements

- Python 3.6+
- Internet connection
- GitHub API token (optional but recommended to avoid rate limits)

## Installation

No installation is required beyond Python 3. The script installs the required Python packages (`tqdm`, `requests`) at runtime if they are missing.

You can also install them manually:

```bash
pip install tqdm requests

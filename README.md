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

pip install tqdm requests

## Usage
Run the script with:

python mistersyscheck5.py

The script will:

Check your GitHub API rate limit.

Retrieve all repositories in the MiSTer-devel organization.

Check each repository (excluding those on the ignore list) for a sys/ folder.

Output a sorted list of matches to the terminal.

Save the results to a CSV file named mister_sys_folders_YYYY-MM-DD_HH-MM-SS.csv.

## Output
Example output in the terminal:

Repositories with 'sys' folder:
Core1 — Last sys/ update: 2024-12-15T10:45:12Z by user123 — Status: Active
Core2 — Last sys/ update: 2023-07-22T18:33:04Z by dev567 — Status: Deprecated

CSV output saved as: mister_sys_folders_2025-05-22_14-55-33.csv

Summary:
Total repositories retrieved: 85
Repositories checked (excluding exceptions): 65
Repositories with a 'sys' folder: 22
Errors encountered: 3

Total runtime: 1 minutes, 42 seconds
Configuration
To increase GitHub API limits, you can provide your own GitHub token by replacing the value of GITHUB_TOKEN in the script:

GITHUB_TOKEN = "your_token_here"
Modify the EXCLUDED_REPOS set to change which repositories are skipped.

## License
MIT License 

import subprocess
import sys

# Check if 'tqdm' is installed and install it if not
try:
    import tqdm
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])

# Similarly for requests
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])

import csv
import logging
from datetime import datetime
import time
from tqdm import tqdm
import threading
import itertools

# Spinner class
class Spinner:
    def __init__(self, message="Working..."):
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])
        self.running = False
        self.thread = None
        self.message = message

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def _spin(self):
        while self.running:
            sys.stdout.write(f"\r{self.message} {next(self.spinner)}")
            sys.stdout.flush()
            time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
        sys.stdout.flush()

# GitHub API setup
GITHUB_TOKEN = ""  # Optional: Add your token here to increase rate limits
ORG = "MiSTer-devel"
API_URL = "https://api.github.com"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# Exceptions list
EXCLUDED_REPOS = {
    "u-boot_MiSTer", "Linux_Image_creator_MiSTer", "Main_MiSTer", "Hardware_MiSTer",
    "SD-InstallTool_Win_MiSTer", "SD-Installer-Win64_MiSTer", "Injector_MiSTer",
    "MiSTer-bootstrap", "Filters_MiSTer", "Updater_script_MiSTer", "Scripts_MiSTer",
    "MiSTer-devel.github.io", "MidiLink_MiSTer", "Fonts_MiSTer", "MiSTerConfigurator",
    "LXDE-Head_MiSTer", "Hardware_alternative", "MRA-Alternatives_MiSTer",
    "Retro-Controllers-USB-MiSTer", "mr-fusion", "xow_MiSTer", "T80", "T65",
    "Distribution_MiSTer", "Linux-Kernel_MiSTer", "Downloader_MiSTer",
    "ShadowMasks_MiSTer", "Presets_MiSTer", "PDFViewer_MiSTer", "MkDocs_MiSTer",
    "ArcadeDatabase_MiSTer", "Gamecontrollerdb_MiSTer", "Wiki_MiSTer",
    "Hiscores_MiSTer", "Cheats_MiSTer", "N64_ROM_Database"
}

# Set up logging to display in the terminal
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

def get_rate_limit_status():
    url = f"{API_URL}/rate_limit"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        remaining = data['resources']['core']['remaining']
        reset_time = data['resources']['core']['reset']
        print(f"Remaining requests: {remaining}, Reset time (epoch): {reset_time}")
        return remaining, reset_time
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for rate limit check: {e}")
        return 0, None

def get_repos():
    repos = []
    page = 1
    while True:
        url = f"{API_URL}/orgs/{ORG}/repos?type=all&per_page=100&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed for repo list: {e}")
            break

        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def check_sys_folder(repo_name):
    url = f"{API_URL}/repos/{ORG}/{repo_name}/contents/sys"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {repo_name}: {e}")
        return None, None

    if resp.status_code == 200:
        commit_url = f"{API_URL}/repos/{ORG}/{repo_name}/commits?path=sys&per_page=1"
        try:
            commit_resp = requests.get(commit_url, headers=HEADERS, timeout=10)
            commit_resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Commit request failed for {repo_name}: {e}")
            return None, None

        if commit_resp.status_code == 200 and commit_resp.json():
            last_commit = commit_resp.json()[0]
            date = last_commit.get('commit', {}).get('committer', {}).get('date', '')
            author_data = last_commit.get('author')
            if author_data and 'login' in author_data:
                author = author_data['login']
            else:
                author = last_commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            return date, author

    return None, None

def main():
    start_time = time.time()

    spinner = Spinner("Checking rate limit")
    spinner.start()
    get_rate_limit_status()
    spinner.stop()

    spinner = Spinner("Fetching repositories")
    spinner.start()
    repos = get_repos()
    spinner.stop()

    results = []

    # Summary counters
    total_repos = 0
    checked_repos = 0
    repos_with_sys = 0
    errors_encountered = 0

    for repo in tqdm(repos, desc="Checking repositories"):
        repo_name = repo['name']
        total_repos += 1

        if repo_name in EXCLUDED_REPOS:
            continue

        checked_repos += 1
        is_archived = repo.get('archived', False)
        status = "Deprecated" if is_archived else "Active"

        date, user = check_sys_folder(repo_name)
        if date:
            repos_with_sys += 1
            results.append((repo_name, date, user, status))
        else:
            errors_encountered += 1

    # Sort the results by date (oldest first)
    results.sort(key=lambda x: datetime.strptime(x[1], "%Y-%m-%dT%H:%M:%SZ"))

    # Output to terminal
    print("\nRepositories with 'sys' folder:")
    for name, date, user, status in results:
        print(f"{name} — Last sys/ update: {date} by {user} — Status: {status}")

    # Write CSV with timestamped filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"mister_sys_folders_{timestamp}.csv"
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Core Name", "Date", "Time", "User", "Status"])
        for name, date, user, status in results:
            if "T" in date:
                date_part, time_part = date.split("T")
                time_part = time_part.replace("Z", "")
            else:
                date_part, time_part = date, ""
            writer.writerow([name, date_part, time_part, user, status])

    print(f"\nCSV output saved as: {filename}")

    # Print summary
    print("\nSummary:")
    print(f"Total repositories retrieved: {total_repos}")
    print(f"Repositories checked (excluding exceptions): {checked_repos}")
    print(f"Repositories with a 'sys' folder: {repos_with_sys}")
    print(f"Errors encountered: {errors_encountered}")

    # Print runtime
    elapsed_time = time.time() - start_time
    minutes, seconds = divmod(int(elapsed_time), 60)
    print(f"\nTotal runtime: {minutes} minutes, {seconds} seconds")

if __name__ == "__main__":
    main()
